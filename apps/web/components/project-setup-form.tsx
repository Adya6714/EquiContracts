"use client";

import { FormEvent, useState } from "react";

import { createProject, type Project } from "@/lib/api";

export function ProjectSetupForm() {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const data = new FormData(event.currentTarget);
    try {
      const created = await createProject({
        name: String(data.get("name")),
        city_code: String(data.get("city_code")),
      });
      setProject(created);
    } catch {
      setError("Project creation failed. Confirm the API and database are running.");
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <form className="card" onSubmit={submit}>
        <label>
          Project name
          <input name="name" required maxLength={200} />
        </label>
        <label>
          City code
          <input
            name="city_code"
            required
            minLength={3}
            maxLength={3}
            pattern="[A-Za-z]{3}"
            placeholder="MUM"
          />
        </label>
        <button type="submit" disabled={pending}>
          {pending ? "Creating…" : "Create project"}
        </button>
        {error ? <p role="alert">{error}</p> : null}
      </form>

      {project ? (
        <section className="card" aria-live="polite">
          <h2>{project.name} is ready</h2>
          <p>
            Project code: <strong>{project.project_code}</strong>
          </p>
          <p>Forward project correspondence to the shared inbox (plus-addressed):</p>
          <p>
            <strong>{project.inbound_email}</strong>
          </p>
        </section>
      ) : null}
    </>
  );
}
