import axios from "axios";
import { getToken } from "./api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "/api";

export const authApi = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

authApi.interceptors.request.use((config) => {
  const token = typeof window !== "undefined" ? getToken() : null;

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});
