"use client";

import {
  useEffect,
  useState,
} from "react";

import {
  useParams,
} from "next/navigation";

import {
  getArticle,
  getRevisions,
  sendToReview,
  rejectArticle,
  approveArticle,
  publishArticle,
} from "@/lib/api";

import {
  getUser,
} from "@/lib/auth";

import {
  Article,
  ArticleRevision,
} from "@/lib/types";

import ArticleEditor from "@/components/ArticleEditor";
import ArticleStatus from "@/components/ArticleStatus";
import SourcePanel from "@/components/SourcePanel";


export default function ReviewPage() {

  const params =
    useParams();

  const id =
    Number(params.id);

  const [article, setArticle] =
    useState<Article | null>(null);

  const [revisions, setRevisions] =
    useState<ArticleRevision[]>([]);

  const [error, setError] =
    useState("");

  const user = getUser();


  async function load() {

    try {

      const [
        articleData,
        revisionsData,
      ] = await Promise.all([
        getArticle(id),
        getRevisions(id),
      ]);

      setArticle(articleData);
      setRevisions(
        revisionsData,
      );

    } catch (err) {

      setError(
        err instanceof Error
          ? err.message
          : "Failed to load",
      );
    }
  }


  useEffect(() => {

    if (id) {
      load();
    }

  }, [id]);


  if (error) {

    return (
      <div className="p-8 text-red-300">
        {error}
      </div>
    );
  }


  if (!article) {

    return (
      <div className="p-8">
        Loading...
      </div>
    );
  }


  async function review() {
    setArticle(
      await sendToReview(id),
    );
  }


  async function reject() {
    setArticle(
      await rejectArticle(
        id,
        "Needs editorial revision",
      ),
    );
  }


  async function approve() {
    setArticle(
      await approveArticle(id),
    );
  }


  async function publish() {
    setArticle(
      await publishArticle(id),
    );
  }


  return (
    <div className="p-8">

      <div className="mb-6 flex items-center justify-between">

        <div>

          <h1 className="text-2xl font-bold">
            Review article
          </h1>

          <div className="mt-2 flex gap-3">

            <ArticleStatus
              status={article.status}
            />

            {article.category && (
              <span className="text-sm text-slate-500">
                {article.category}
              </span>
            )}

          </div>

        </div>


        <div className="flex gap-2">

          {article.status === "draft" &&
            (
              <button
                onClick={review}
                className="rounded-lg bg-yellow-600 px-4 py-2 text-sm font-medium"
              >
                Send to review
              </button>
            )}


          {article.status ===
            "ready_for_review" &&
            user &&
            (
              <>
                {(user.role ===
                  "editor" ||
                  user.role ===
                    "publisher") && (
                  <button
                    onClick={reject}
                    className="rounded-lg border border-red-700 px-4 py-2 text-sm text-red-300"
                  >
                    Reject
                  </button>
                )}

                {(user.role ===
                  "editor" ||
                  user.role ===
                    "publisher") && (
                  <button
                    onClick={approve}
                    className="rounded-lg bg-blue-600 px-4 py-2 text-sm"
                  >
                    Approve
                  </button>
                )}
              </>
            )}


          {article.status ===
            "approved" &&
            user?.role ===
              "publisher" && (

              <button
                onClick={publish}
                className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium"
              >
                Publish
              </button>
            )}

        </div>

      </div>


      <div className="grid grid-cols-[1fr_320px] gap-6">

        <ArticleEditor
          article={article}
          onSaved={setArticle}
        />

        <div className="space-y-6">

          <SourcePanel />


          <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">

            <h2 className="mb-4 font-semibold">
              Revision history
            </h2>


            <div className="space-y-4">

              {revisions.map(
                revision => (

                  <div
                    key={revision.id}
                    className="border-l-2 border-slate-700 pl-4"
                  >

                    <div className="text-sm font-medium">
                      Revision{" "}
                      {
                        revision.revision_number
                      }
                    </div>

                    <div className="mt-1 text-xs text-slate-500">
                      {revision.editor_name ||
                        "AI"}
                    </div>

                    <div className="mt-2 text-xs text-slate-400">
                      {
                        revision.change_summary ||
                        "No description"
                      }
                    </div>

                  </div>
                ),
              )}

            </div>

          </section>

        </div>

      </div>

    </div>
  );
}