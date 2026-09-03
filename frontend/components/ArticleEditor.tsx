"use client";

import { useState } from "react";
import {
  Save,
  CheckCircle,
} from "lucide-react";

import {
  Article,
} from "@/lib/types";

import {
  updateArticle,
} from "@/lib/api";


export default function ArticleEditor({
  article,
  onSaved,
}: {
  article: Article;
  onSaved?: (
    article: Article,
  ) => void;
}) {

  const [title, setTitle] =
    useState(article.title);

  const [subtitle, setSubtitle] =
    useState(
      article.subtitle || "",
    );

  const [content, setContent] =
    useState(article.content);

  const [saving, setSaving] =
    useState(false);

  const [saved, setSaved] =
    useState(false);

  const [error, setError] =
    useState("");


  async function save() {

    setSaving(true);
    setSaved(false);
    setError("");

    try {

      const updated =
        await updateArticle(
          article.id,
          {
            title,
            subtitle,
            content,
            version:
              article.version,

            change_summary:
              "Editorial revision",
          },
        );

      setSaved(true);

      onSaved?.(updated);

      setTimeout(
        () => setSaved(false),
        2500,
      );

    } catch (err) {

      setError(
        err instanceof Error
          ? err.message
          : "Save failed",
      );

    } finally {

      setSaving(false);
    }
  }


  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900">

      <div className="flex items-center justify-between border-b border-slate-800 p-4">

        <div>
          <h2 className="font-semibold">
            Article
          </h2>

          <div className="mt-1 text-xs text-slate-500">
            Version {article.version}
            {" · "}
            {article.word_count ?? 0}
            {" words"}
          </div>
        </div>


        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-500 disabled:opacity-50"
        >

          {saved ? (
            <>
              <CheckCircle size={16} />
              Saved
            </>
          ) : (
            <>
              <Save size={16} />
              {saving
                ? "Saving..."
                : "Save"}
            </>
          )}

        </button>

      </div>


      {error && (
        <div className="m-4 rounded-lg bg-red-950 p-3 text-sm text-red-300">
          {error}
        </div>
      )}


      <div className="p-5">

        <input
          value={title}
          onChange={(e) =>
            setTitle(e.target.value)
          }
          className="w-full bg-transparent text-2xl font-bold outline-none"
        />


        <input
          value={subtitle}
          onChange={(e) =>
            setSubtitle(e.target.value)
          }
          placeholder="Subtitle"
          className="mt-3 w-full bg-transparent text-lg text-slate-400 outline-none"
        />


        <textarea
          value={content}
          onChange={(e) =>
            setContent(e.target.value)
          }
          className="mt-6 min-h-[600px] w-full rounded-lg border border-slate-800 bg-slate-950 p-5 text-[15px] leading-7 outline-none focus:border-blue-500"
        />

      </div>

    </section>
  );
}