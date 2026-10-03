import "server-only";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export interface VerifiedProjectSummary {
  id: string;
  name: string;
  project_code: string;
  verified_field_count: number;
}

export async function getVerifiedClientDashboard(): Promise<
  VerifiedProjectSummary[]
> {
  const response = await fetch(`${API_URL}/client/dashboard`, {
    headers: {
      "x-user-id":
        process.env.CLIENT_USER_ID ?? "10000000-0000-4000-8000-000000000002",
      "x-org-id":
        process.env.CLIENT_ORG_ID ?? "00000000-0000-4000-8000-000000000002",
      "x-org-type": "client",
      "x-role": "client_pm",
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Client dashboard could not be loaded");
  }
  return response.json() as Promise<VerifiedProjectSummary[]>;
}
