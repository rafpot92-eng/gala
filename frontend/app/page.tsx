"use client";

import {
  useEffect,
  useState,
} from "react";

import {
  getArticles,
} from "@/lib/api";

import {
  Article,
} from "@/lib/types";

import ArticleStatus from "@/components/ArticleStatus";

import Link from "next/link";


export default function Dashboard() {

  const [articles, setArticles] =
    useState<Article[]>([]);


  useEffect(() => {

    getArticles()
      .then(setArticles)
      .catch(console.error);

  }, []);


  const counts = {
    draft: articles.filter(
      a => a.status === "draft",
    ).length,

    review: articles.filter(
      a =>
        a.status ===
        "ready_for_review",
    ).length,

    approved: articles.filter(
      a =>
        a.status === "approved",
    ).length,

    published: articles.filter(
      a =>
        a.status === "published",
    ).length,
  };


  return (
    <div className="p-8">

      <h1 className="text-3xl font-bold">
        Dashboard
      </h1>

      <p className="mt-2 text-slate-500">
        Editorial overview
      </p>


      <div className="mt-8 grid grid-cols-4 gap-4">

        <Stat
          label="Draft"
          value={counts.draft}
        />

        <Stat
          label="Review"
          value={counts.review}
        />

        <Stat
          label="Approved"
          value={counts.approved}
        />

        <Stat
          label="Published"
          value={counts.published}
        />

      </div>


      <section className="mt-8">

        <h2 className="mb-4 text-xl font-semibold">
          Recent articles
        </h2>

        <div className="space-y-2">

          {articles
            .slice(0, 10)
            .map(article => (

              <Link
                key={article.id}
                href={`/review/${article.id}`}
                className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900 p-4 hover:border-slate-600"
              >

                <div>
                  <div className="font-medium">
                    {article.title}
                  </div>

                  <div className="mt-1 text-xs text-slate-500">
                    {article.category}
                  </div>
                </div>

                <ArticleStatus
                  status={
                    article.status
                  }
                />

              </Link>

            ))}

        </div>

      </section>

    </div>
  );
}


function Stat({
  label,
  value,
}: {
  label: string;
  value: number;
}) {

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">

      <div className="text-sm text-slate-500">
        {label}
      </div>

      <div className="mt-2 text-3xl font-bold">
        {value}
      </div>

    </div>
  );
}