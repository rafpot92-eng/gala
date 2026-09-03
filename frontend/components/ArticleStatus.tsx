import { ArticleStatus } from "@/lib/types";


export default function ArticleStatus({
  status,
}: {
  status: ArticleStatus;
}) {

  const styles: Record<
    ArticleStatus,
    string
  > = {

    draft:
      "bg-slate-800 text-slate-300",

    ready_for_review:
      "bg-yellow-900/50 text-yellow-300",

    approved:
      "bg-blue-900/50 text-blue-300",

    published:
      "bg-green-900/50 text-green-300",
  };


  const labels: Record<
    ArticleStatus,
    string
  > = {

    draft: "Draft",

    ready_for_review:
      "Ready for review",

    approved:
      "Approved",

    published:
      "Published",
  };


  return (
    <span
      className={`rounded-full px-3 py-1 text-xs ${styles[status]}`}
    >
      {labels[status]}
    </span>
  );
}