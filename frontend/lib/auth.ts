import { User } from "./types";

export async function getCurrentUser(): Promise<User | null> {

  try {

    const response = await fetch(
      `${
        process.env.NEXT_PUBLIC_API_URL ||
        "http://localhost:8000"
      }/api/auth/me`,
      {
        credentials: "include",
        cache: "no-store",
      },
    );

    if (!response.ok) {
      return null;
    }

    return response.json();

  } catch {

    return null;
  }
}


export function login() {

  window.location.href =
    `${
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000"
    }/api/auth/login`;
}


export async function logout() {

  await fetch(
    `${
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000"
    }/api/auth/logout`,
    {
      method: "POST",
      credentials: "include",
    },
  );

  window.location.href =
    "/login";
}