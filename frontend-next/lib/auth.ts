import { authApi } from "./auth-api";
import {
  getToken as getStoredToken,
  isPersistentAuth,
  logoutSession,
  storeAuth,
} from "./api";

export function getToken() {
  return getStoredToken();
}

export function setToken(token: string, rememberMe = false) {
  storeAuth(token, undefined, rememberMe);
}

export function logout() {
  void logoutSession();
}

export async function loadUser() {
  const res = await authApi.get("/account/me");
  const token = getStoredToken();
  if (token) storeAuth(token, res.data, isPersistentAuth());
  return res.data;
}
