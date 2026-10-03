const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const contractorHeaders = {
  "content-type": "application/json",
  "x-user-id":
    process.env.NEXT_PUBLIC_CONTRACTOR_USER_ID ??
    "10000000-0000-4000-8000-000000000001",
  "x-org-id":
    process.env.NEXT_PUBLIC_CONTRACTOR_ORG_ID ??
    "00000000-0000-4000-8000-000000000001",
  "x-org-type": "contractor",
  "x-role": "contractor_admin",
};

export interface Project {
  id: string;
  name: string;
  project_code: string;
  inbound_email: string;
}

export interface ReviewItem {
  document_id: string;
  filename: string;
  field_id: string | null;
  field_name: string | null;
  field_value: string | null;
  state: string | null;
  is_financial: boolean | null;
}

export async function createProject(input: {
  name: string;
  city_code: string;
}): Promise<Project> {
  const response = await fetch(`${API_URL}/projects`, {
    method: "POST",
    headers: contractorHeaders,
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error("Project could not be created");
  }
  return response.json() as Promise<Project>;
}

export async function getReviewQueue(): Promise<ReviewItem[]> {
  const response = await fetch(`${API_URL}/review/queue`, {
    headers: contractorHeaders,
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Review queue could not be loaded");
  }
  return response.json() as Promise<ReviewItem[]>;
}
