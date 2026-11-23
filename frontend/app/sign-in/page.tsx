import { Header } from "@/components/layout/header";
import { SignInForm } from "@/components/auth/sign-in-form";
import "../sky.css";
import "../home.css";
import "../feature-pages.css";
import "../readability.css";
export default async function SignIn({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const params = await searchParams;
  return (
    <div className="feature-site sky-home">
      <Header />
      <main className="feature-content home-width sign-in-main">
        <div className="career-workspace">
          <SignInForm initialError={params.error} />
        </div>
      </main>
    </div>
  );
}
