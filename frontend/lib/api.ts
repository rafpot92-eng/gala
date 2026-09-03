import {
  Article,
  ArticleRevision,
  User,
} from "./types";


const API =
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";


async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {

  const response = await fetch(
    `${API}${path}`,
    {
      ...options,

      credentials: "include",

      headers: {
        "Content-Type":
          "application/json",

        ...(options.headers || {}),
      },
    },
  );


  if (
    response.status === 401
  ) {

    if (
      typeof window !==
      "undefined"
    ) {

      window.location.href =
        "/login";
    }

    throw new Error(
      "Authentication required",
    );
  }


  if (!response.ok) {

    const body =
      await response
        .json()
        .catch(() => null);

    throw new Error(
      body?.detail ||
      "Request failed",
    );
  }


  return response.json();
}


export async function getCurrentUser() {

  return request<User>(
    "/api/auth/me",
  );
}


export async function logout() {

  return request(
    "/api/auth/logout",
    {
      method: "POST",
    },
  );
}


export async function getArticles(
  status?: string,
) {

  const query = status
    ? `?status=${encodeURIComponent(
        status,
      )}`
    : "";

  return request<Article[]>(
    `/api/generated${query}`,
  );
}


export async function getArticle(
  id: number,
) {

  return request<Article>(
    `/api/generated/${id}`,
  );
}


export async function updateArticle(
  id: number,
  data: {
    title: string;
    subtitle?: string;
    content: string;
    change_summary?: string;
    version: number;
  },
) {

  return request<Article>(
    `/api/generated/${id}`,
    {
      method: "PATCH",

      body: JSON.stringify(
        data,
      ),
    },
  );
}


export async function sendToReview(
  id: number,
) {

  return request<Article>(
    `/api/generated/${id}/review`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}


export async function rejectArticle(
  id: number,
  notes?: string,
) {

  return request<Article>(
    `/api/generated/${id}/reject`,
    {
      method: "POST",

      body: JSON.stringify({
        notes,
      }),
    },
  );
}


export async function approveArticle(
  id: number,
) {

  return request<Article>(
    `/api/generated/${id}/approve`,
    {
      method: "POST",

      body: JSON.stringify({}),
    },
  );
}


export async function publishArticle(
  id: number,
) {

  return request<Article>(
    `/api/generated/${id}/publish`,
    {
      method: "POST",

      body: JSON.stringify({}),
    },
  );
}


export async function getRevisions(
  id: number,
) {

  return request<ArticleRevision[]>(
    `/api/generated/${id}/revisions`,
  );
}


export async function searchArticles(
  query: string,
) {

  return request<Article[]>(
    `/api/search?q=${encodeURIComponent(
      query,
    )}`,
  );
}