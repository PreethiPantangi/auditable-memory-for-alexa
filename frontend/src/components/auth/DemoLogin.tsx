import { useState, type FormEvent } from "react";
import "./DemoLogin.css";

type DemoLoginProps = {
  onLogin: (username: string, password: string) => Promise<void>;
};

export default function DemoLogin({ onLogin }: DemoLoginProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    const normalizedUsername = username.trim();

    if (!normalizedUsername || !password) {
      setError("Enter a username and password.");
      return;
    }

    try {
      setLoading(true);
      await onLogin(normalizedUsername, password);
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Login failed. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <form onSubmit={handleSubmit} className="login-card">
        <h1>Auditable Memory</h1>
        <p>Sign in to your demo account.</p>

        <label htmlFor="username">Username</label>
        <input
          id="username"
          name="username"
          type="text"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          required
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />

        {error && <p role="alert">{error}</p>}

        <button type="submit" disabled={loading}>
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}
