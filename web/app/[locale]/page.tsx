import {useTranslations} from "next-intl";
import Link from "next/link";

import {SubscribeForm} from "@/components/SubscribeForm";

const STEPS = [
  {
    icon: (
      <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" />
      </svg>
    ),
    key: "step1",
  },
  {
    icon: (
      <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
      </svg>
    ),
    key: "step2",
  },
  {
    icon: (
      <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 14.25v2.25m3-4.5v4.5m3-6.75v6.75m3-9v9M6 20.25h12A2.25 2.25 0 0 0 20.25 18V6A2.25 2.25 0 0 0 18 3.75H6A2.25 2.25 0 0 0 3.75 6v12A2.25 2.25 0 0 0 6 20.25Z" />
      </svg>
    ),
    key: "step3",
  },
  {
    icon: (
      <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
      </svg>
    ),
    key: "step4",
  },
];

export default function LandingPage() {
  const t = useTranslations("landing");
  const nav = useTranslations("nav");

  return (
    <div className="space-y-16 py-8">
      {/* Hero */}
      <section className="mx-auto max-w-2xl text-center">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
          {t("headline")}
        </h1>
        <p className="mt-4 text-lg text-gray-600 dark:text-slate-400">
          {t("subtitle")}
        </p>
        <div className="mt-8">
          <SubscribeForm />
        </div>
      </section>

      {/* How it works */}
      <section>
        <h2 className="mb-8 text-center text-xl font-bold">{t("howItWorks")}</h2>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, i) => (
            <div
              key={step.key}
              className="flex flex-col items-center rounded-lg border border-gray-200 bg-white p-6 text-center dark:border-slate-700 dark:bg-slate-800"
            >
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-accent/10 text-accent dark:bg-accent/20">
                {step.icon}
              </div>
              <span className="mt-2 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500">
                {i + 1}
              </span>
              <p className="mt-2 text-sm font-medium text-gray-700 dark:text-slate-300">
                {t(step.key)}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Trust / Auditability */}
      <section className="mx-auto max-w-xl text-center">
        <div className="rounded-lg border border-gray-200 bg-white p-8 dark:border-slate-700 dark:bg-slate-800">
          <svg
            className="mx-auto h-10 w-10 text-accent"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z"
            />
          </svg>
          <h3 className="mt-4 text-lg font-bold">{t("trustTitle")}</h3>
          <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
            {t("trustDescription")}
          </p>
          <Link
            href="./analytics/evidence"
            className="mt-4 inline-block text-sm font-semibold text-accent hover:underline"
          >
            {nav("audit")} →
          </Link>
        </div>
      </section>

    </div>
  );
}
