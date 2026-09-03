export type Role =
  | "viewer"
  | "editor"
  | "publisher";

export type ArticleStatus =
  | "draft"
  | "ready_for_review"
  | "approved"
  | "published";


export interface User {
  id: number;
  email: string;
  name?: string;
  role: Role;
}


export interface Article {
  id: number;
  title: string;
  subtitle?: string;
  content: string;
  category?: string;
  status: ArticleStatus;
  word_count?: number;
  created_at: string;
  updated_at: string;
  published_at?: string;
  version: number;
}


export interface ArticleRevision {
  id: number;
  revision_number: number;
  title: string;
  subtitle?: string;
  content: string;
  change_summary?: string;
  created_at: string;
  editor_name?: string;
  editor_email?: string;
}