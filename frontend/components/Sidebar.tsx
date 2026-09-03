"use client";

import Link from "next/link";

import {
  useEffect,
  useState,
} from "react";

import {
  LayoutDashboard,
  Newspaper,
  Search,
  LogOut,
} from "lucide-react";

import {
  getCurrentUser,
  logout,
} from "@/lib/auth";

import {
  User,
} from "@/lib/types";


export default function Sidebar() {

  const [user, setUser] =
    useState<User | null>(null);


  useEffect(() => {

    getCurrentUser()
      .then(setUser);

  }, []);


  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-950 p-5">

      <div className="mb-8">

        <div className="text-xl font-bold">
          Meczyki
        </div>

        <div className="text-xs text-slate-500">
          Editorial
        </div>

      </div>


      <nav className="space-y-2">

        <Link
          href="/"
          className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-slate-900"
        >
          <LayoutDashboard size={18} />
          Dashboard
        </Link>


        <Link
          href="/articles"
          className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-slate-900"
        >
          <Newspaper size={18} />
          Articles
        </Link>


        <Link
          href="/search"
          className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-slate-900"
        >
          <Search size={18} />
          Search
        </Link>

      </nav>


      <div className="absolute bottom-5 w-52 border-t border-slate-800 pt-4">

        <div className="text-sm">
          {user?.name ||
            user?.email ||
            "Loading..."}
        </div>

        <div className="mb-3 text-xs text-slate-500">
          {user?.role}
        </div>


        <button
          onClick={logout}
          className="flex items-center gap-2 text-sm text-slate-400 hover:text-white"
        >
          <LogOut size={16} />
          Logout
        </button>

      </div>

    </aside>
  );
}