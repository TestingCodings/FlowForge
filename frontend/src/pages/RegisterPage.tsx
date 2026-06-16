import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";

import { register as registerUser } from "../api/auth";

interface RegisterForm {
  email: string;
  first_name: string;
  last_name: string;
  password: string;
  password_confirm: string;
}

export default function RegisterPage() {
  const { register, handleSubmit } = useForm<RegisterForm>();
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const onSubmit = async (data: RegisterForm) => {
    setError("");
    try {
      await registerUser(data);
      navigate("/login");
    } catch {
      setError("Registration failed");
    }
  };

  return (
    <div className="app-shell" style={{ maxWidth: 520 }}>
      <div className="card">
        <h2>Create account</h2>
        <form className="grid" onSubmit={handleSubmit(onSubmit)}>
          <div>
            <label>Email</label>
            <input {...register("email")} type="email" required />
          </div>
          <div className="grid two">
            <div>
              <label>First name</label>
              <input {...register("first_name")} required />
            </div>
            <div>
              <label>Last name</label>
              <input {...register("last_name")} required />
            </div>
          </div>
          <div>
            <label>Password</label>
            <input {...register("password")} type="password" required />
          </div>
          <div>
            <label>Confirm password</label>
            <input {...register("password_confirm")} type="password" required />
          </div>
          {error && <p className="error">{error}</p>}
          <button type="submit">Register</button>
        </form>
        <p style={{ marginTop: 10 }}>
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
