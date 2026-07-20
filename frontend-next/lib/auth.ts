import { authApi } from "./auth-api";

export function getToken() {
  return localStorage.getItem("access_token");
}

export function setToken(token: string) {
  localStorage.setItem("access_token", token);
}

export function logout() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("user");
}

export async function loadUser() {
  const res = await authApi.get("/account/me");
  localStorage.setItem("user", JSON.stringify(res.data));
  return res.data;
}