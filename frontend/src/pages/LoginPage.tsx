import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../api/client";
import { login } from "../api/auth";
import { DemoInfo } from "../types/api";
import { useTranslation } from "../i18n";

interface LoginForm {
  email: string;
  password: string;
}

export default function LoginPage() {
  const { t } = useTranslation();
  const { register, handleSubmit, setValue } = useForm<LoginForm>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  // Public endpoint: empty on any non-demo deployment.
  const { data: demo } = useQuery<DemoInfo>({
    queryKey: ["demo-info"],
    queryFn: async () => (await apiClient.get("/demo-info/")).data,
    staleTime: Infinity,
    retry: false,
  });

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
          <p>{t("page.login.subtitle")}</p>
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

        {/* Demo accounts come from /api/demo-info/, which serves them only
            when the deployment sets DEMO_MODE. Hard-coding them here put
            working credentials in a public source file; now they are
            deployment config and this renders nothing anywhere else. */}
        {demo?.demo_mode && demo.accounts.length > 0 && (
          <>
            <div className="divider" />
            {demo.notice && (
              <div className="text-xs text-muted" style={{ textAlign: "center", marginBottom: 8 }}>
                {demo.notice}
              </div>
            )}
            <div className="text-xs text-muted" style={{ textAlign: "center" }}>
              <div style={{ marginBottom: 4, fontWeight: 600 }}>Demo accounts</div>
              {demo.accounts.map((a) => (
                <button
                  key={a.email}
                  type="button"
                  className="btn-ghost btn-sm"
                  style={{ display: "block", margin: "0 auto" }}
                  onClick={() => { setValue("email", a.email); setValue("password", a.password); }}
                >
                  {a.role ? `${a.role} — ` : ""}{a.email}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
