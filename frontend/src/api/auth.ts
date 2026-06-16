import { apiClient } from "./client";

export async function login(email: string, password: string) {
  const response = await apiClient.post("/auth/login/", { email, password });
  return response.data;
}

export async function register(payload: {
  email: string;
  first_name: string;
  last_name: string;
  password: string;
  password_confirm: string;
}) {
  const response = await apiClient.post("/auth/register/", payload);
  return response.data;
}
