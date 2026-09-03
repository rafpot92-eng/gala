"use client";

import { useEffect } from "react";

import {
  login,
  getCurrentUser,
} from "@/lib/auth";


export default function LoginPage() {

  useEffect(() => {

    getCurrentUser()
      .then(user => {

        if (user) {
          window.location.href =
            "/";
        }

      });

  }, []);


  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950">

      <div className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-8">

        <div className="text-2xl font-bold">
          Meczyki Editorial
        </div>

        <p className="mt-2 text-sm text-slate-500">
          Editorial workspace
        </p>


        <button
          onClick={login}
          className="mt-8 w-full rounded-lg bg-blue-600 py-3 font-medium hover:bg-blue-500"
        >
          Continue with Databricks
        </button>


        <p className="mt-5 text-center text-xs text-slate-600">
          Authentication is handled by
          Databricks.
        </p>

      </div>

    </main>
  );
}