/**
 * Express route handlers for the API.
 * Known symbols: createUser, getUsers, deleteUser, validatePayload
 */

const validatePayload = (body) => {
  if (!body.name || typeof body.name !== "string") {
    return { valid: false, error: "name is required and must be a string" };
  }
  if (!body.email || !body.email.includes("@")) {
    return { valid: false, error: "valid email is required" };
  }
  return { valid: true };
};

const createUser = async (req, res) => {
  const { valid, error } = validatePayload(req.body);
  if (!valid) {
    return res.status(400).json({ error });
  }

  try {
    const user = await db.users.create({
      name: req.body.name,
      email: req.body.email,
      role: req.body.role || "viewer",
    });
    res.status(201).json(user);
  } catch (err) {
    if (err.code === "UNIQUE_VIOLATION") {
      return res.status(409).json({ error: "user already exists" });
    }
    res.status(500).json({ error: "internal server error" });
  }
};

const getUsers = async (req, res) => {
  const page = parseInt(req.query.page) || 1;
  const limit = Math.min(parseInt(req.query.limit) || 20, 100);
  const offset = (page - 1) * limit;

  const users = await db.users.findAll({ limit, offset });
  res.json({ users, page, limit, total: users.length });
};

const deleteUser = async (req, res) => {
  const { id } = req.params;
  const result = await db.users.delete(id);
  if (!result) {
    return res.status(404).json({ error: "user not found" });
  }
  res.status(204).send();
};

module.exports = { createUser, getUsers, deleteUser, validatePayload };
