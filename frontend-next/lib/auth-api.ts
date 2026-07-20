import axios from "axios";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "/api";

export const authApi = axios.create({
  baseURL: API_BASE,
});

authApi.interceptors.request.use((config) => {
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("access_token")
      : null;

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});