import { getVerifiedClientDashboard } from "@/lib/client-api";

export const dynamic = "force-dynamic";

export default async function ClientDashboardPage() {
  const projects = await getVerifiedClientDashboard();

  return (
    <>
      <h1>Project dashboard</h1>
      <p className="muted">
        This view contains verified records only. Draft extraction and internal
        contractor notes are excluded by the API and database policies.
      </p>
      {projects.map((project) => (
        <article className="card" key={project.id}>
          <h2>{project.name}</h2>
          <p>{project.project_code}</p>
          <p>
            Verified fields: <strong>{project.verified_field_count}</strong>
          </p>
        </article>
      ))}
    </>
  );
}
