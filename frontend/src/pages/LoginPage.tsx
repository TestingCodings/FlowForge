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
  const navigate = useNavigate();

  const onSubmit = async (data: LoginForm) => {
    setError("");
    try {
      const response = await login(data.email, data.password);
      localStorage.setItem("ff_access_token", response.access);
      localStorage.setItem("ff_refresh_token", response.refresh);
      navigate("/dashboard");
    } catch {
      setError("Invalid credentials");
    }
  };

  return (
    <div className="app-shell" style={{ maxWidth: 440 }}>
      <div className="card">
        <h2>Sign in</h2>
        <form className="grid" onSubmit={handleSubmit(onSubmit)}>
          <div>
            <label>Email</label>
            <input {...register("email")} type="email" required />
          </div>
          <div>
            <label>Password</label>
            <input {...register("password")} type="password" required />
          </div>
          {error && <p className="error">{error}</p>}
          <button type="submit">Login</button>
        </form>
        <p style={{ marginTop: 10 }}>
          No account? <Link to="/register">Register</Link>
        </p>
      </div>
    </div>
  );
}
