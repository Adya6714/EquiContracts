import { getReviewQueue } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ReviewPage() {
  const items = await getReviewQueue();

  return (
    <>
      <h1>Inbox review</h1>
      <p className="muted">
        Documents and extracted fields that still need contractor confirmation.
      </p>
      {items.length === 0 ? (
        <div className="card">Nothing needs review.</div>
      ) : (
        items.map((item) => (
          <article className="card" key={item.field_id ?? item.document_id}>
            <h2>{item.filename}</h2>
            {item.field_name ? (
              <>
                <p>
                  {item.field_name}: {item.field_value ?? "Not present"}
                </p>
                <span className="status">{item.state}</span>
              </>
            ) : (
              <span className="status">Awaiting extraction</span>
            )}
          </article>
        ))
      )}
    </>
  );
}
