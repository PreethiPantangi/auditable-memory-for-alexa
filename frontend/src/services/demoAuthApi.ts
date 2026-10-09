const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export interface DemoSession {
  authenticated: boolean;
  username?: string;
}

export async function loginDemo(
  username: string,
  password: string,
): Promise<DemoSession> {
  const response = await fetch(`${API_BASE_URL}/demo/login`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      username,
      password,
    }),
  });

  if (!response.ok) {
    throw new Error("Invalid username or password.");
  }

  return response.json();
}

export async function checkDemoSession(): Promise<DemoSession> {
  const response = await fetch(`${API_BASE_URL}/demo/session`, {
    method: "GET",
    credentials: "include",
  });

  if (response.status === 401 || response.status === 403) {
    return { authenticated: false };
  }

  if (!response.ok) {
    throw new Error("Unable to check demo session.");
  }

  return response.json();
}

export async function logoutDemo(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/demo/logout`, {
    method: "POST",
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Unable to log out.");
  }
}
