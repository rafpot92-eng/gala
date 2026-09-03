"use client";

import {
  useEffect,
  useState,
} from "react";

import Link from "next/link";

import {
  getArticles,
} from "@/lib/api";

import {
  Article,
} from "@/lib/types";

import ArticleStatus from "@/components/ArticleStatus";


export default function ArticlesPage() {

  const [articles, setArticles] =
    useState<Article[]>([]);

  const [status, setStatus] =
    useState("");


  useEffect(() => {

    getArticles(
      status || undefined,
    )
      .then(setArticles)
      .catch(console.error);

  }, [status]);


  return (
    <div className="p-8">

      <div className="flex items-center justify-between">

        <div>
          <h1 className="text-3xl font-bold">
            Articles
          </h1>

          <p className="mt-2 text-slate-500">
            Manage generated articles.
          </p>
        </div>


        <select
          value={status}
          onChange={e =>
            setStatus(e.target.value)
          }
          className="rounded-lg border border-slate-700 bg-slate-900 p-2"
        >
          <option value="">
            All statuses
          </option>

          <option value="draft">
            Draft
          </option>

          <option value="ready_for_review">
            Ready for review
          </option>

          <option value="approved">
            Approved
          </option>

          <option value="published">
            Published
          </option>

        </select>

      </div>


      <div className="mt-8 space-y-3">

        {articles.map(article => (

          <Link
            key={article.id}
            href={`/review/${article.id}`}
            className="block rounded-xl border border-slate-800 bg-slate-900 p-5 hover:border-slate-600"
          >

            <div className="flex items-center justify-between">

              <div>

                <h2 className="font-semibold">
                  {article.title}
                </h2>

                {article.subtitle && (
                  <p className="mt-1 text-sm text-slate-500">
                    {article.subtitle}
                  </p>
                )}

              </div>

              <ArticleStatus
                status={article.status}
              />

            </div>

          </Link>

        ))}

      </div>

    </div>
  );
}