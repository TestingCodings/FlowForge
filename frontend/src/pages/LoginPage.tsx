import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { login } from "../api/auth";

interface LoginForm {
  email: string;
  password: string;
}

export default function LoginPage() {
  const { register, handleSubmit } = useForm<LoginForm>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const onSubmit = async (data: LoginForm) => {
    setError("");
    setLoading(true);
    try {
      const response = await login(data.email, data.password);
      localStorage.setItem("ff_access_token", response.access);
      localStorage.setItem("ff_refresh_token", response.refresh);
      navigate("/dashboard");
    } catch {
      setError("Invalid email or password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ background: "linear-gradient(135deg, #818cf8, #6366f1)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            FlowForge
          </h2>
          <p>Sign in to your workspace</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="form-group">
            <label>Email address</label>
            <input {...register("email")} type="email" placeholder="you@example.com" required />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input {...register("password")} type="password" placeholder="••••••••" required />
          </div>

          {error && <div className="alert alert-error" style={{ marginBottom: 12 }}>{error}</div>}

          <button type="submit" className="btn-primary w-full" disabled={loading} style={{ justifyContent: "center", marginTop: 4 }}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="text-sm text-muted" style={{ textAlign: "center", marginTop: 20 }}>
          No account? <Link to="/register" style={{ color: "var(--accent-light)" }}>Register</Link>
        </p>

        <div className="divider" />
        <div className="text-xs text-muted" style={{ textAlign: "center" }}>
          Demo: admin@flowforge.dev / Admin1234!
        </div>
      </div>
    </div>
  );
}
