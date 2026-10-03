import { ProjectSetupForm } from "@/components/project-setup-form";

export default function SetupPage() {
  return (
    <>
      <h1>Project setup</h1>
      <p className="muted">
        Create a project and get the address contractors forward documents to.
      </p>
      <ProjectSetupForm />
    </>
  );
}
