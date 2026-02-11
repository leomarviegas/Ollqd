/**
 * Simple TypeScript Express-like app for testing.
 * Known symbols: Router, handleRequest, UserService, AuthMiddleware
 */

interface User {
  id: number;
  name: string;
  role: "admin" | "user";
}

interface RouteHandler {
  method: "GET" | "POST" | "PUT" | "DELETE";
  path: string;
  handler: (req: Request, res: Response) => void;
}

class UserService {
  private users: Map<number, User> = new Map();

  addUser(user: User): void {
    this.users.set(user.id, user);
  }

  getUser(id: number): User | undefined {
    return this.users.get(id);
  }

  listUsers(): User[] {
    return Array.from(this.users.values());
  }

  deleteUser(id: number): boolean {
    return this.users.delete(id);
  }
}

function AuthMiddleware(token: string): boolean {
  // Simple token validation for demonstration
  return token.startsWith("Bearer ") && token.length > 20;
}

class Router {
  private routes: RouteHandler[] = [];

  get(path: string, handler: RouteHandler["handler"]): void {
    this.routes.push({ method: "GET", path, handler });
  }

  post(path: string, handler: RouteHandler["handler"]): void {
    this.routes.push({ method: "POST", path, handler });
  }

  handleRequest(method: string, path: string): RouteHandler | undefined {
    return this.routes.find((r) => r.method === method && r.path === path);
  }
}

export { Router, UserService, AuthMiddleware };
