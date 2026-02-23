import {describe, expect, it} from "vitest";

import en from "../messages/en.json";
import fa from "../messages/fa.json";

describe("translation keys parity", () => {
  function collectKeys(obj: Record<string, unknown>, prefix = ""): string[] {
    const keys: string[] = [];
    for (const key of Object.keys(obj)) {
      const fullKey = prefix ? `${prefix}.${key}` : key;
      const value = obj[key];
      if (typeof value === "object" && value !== null && !Array.isArray(value)) {
        keys.push(...collectKeys(value as Record<string, unknown>, fullKey));
      } else {
        keys.push(fullKey);
      }
    }
    return keys;
  }

  it("fa and en have identical key sets", () => {
    const faKeys = collectKeys(fa).sort();
    const enKeys = collectKeys(en).sort();
    expect(faKeys).toEqual(enKeys);
  });

  it("contains required nav keys", () => {
    expect(fa.nav.home).toBeTruthy();
    expect(fa.nav.analytics).toBeTruthy();
    expect(fa.nav.dashboard).toBeTruthy();
    expect(fa.nav.about).toBeTruthy();
    expect(fa.nav.audit).toBeTruthy();
    expect(fa.nav.ops).toBeTruthy();
    expect(en.nav.home).toBeTruthy();
    expect(en.nav.analytics).toBeTruthy();
    expect(en.nav.ops).toBeTruthy();
  });

  it("contains required common keys", () => {
    expect(fa.common.appTitle).toBeTruthy();
    expect(fa.common.loading).toBeTruthy();
    expect(fa.common.error).toBeTruthy();
    expect(fa.common.login).toBeTruthy();
    expect(fa.common.logout).toBeTruthy();
    expect(en.common.appTitle).toBeTruthy();
    expect(en.common.login).toBeTruthy();
  });

  it("contains landing page keys", () => {
    expect(fa.landing.headline).toBeTruthy();
    expect(fa.landing.subtitle).toBeTruthy();
    expect(fa.landing.successMessage).toBeTruthy();
    expect(fa.landing.errorMessage).toBeTruthy();
    expect(fa.landing.howItWorks).toBeTruthy();
    expect(fa.landing.step1).toBeTruthy();
    expect(fa.landing.step4).toBeTruthy();
    expect(fa.landing.joinCta).toBeTruthy();
    expect(en.landing.headline).toBeTruthy();
    expect(en.landing.successMessage).toBeTruthy();
    expect(en.landing.joinCta).toBeTruthy();
  });

  it("contains signup page keys", () => {
    expect(fa.signup.title).toBeTruthy();
    expect(fa.signup.stepEmail).toBeTruthy();
    expect(fa.signup.stepTelegram).toBeTruthy();
    expect(fa.signup.emailSubmit).toBeTruthy();
    expect(fa.signup.emailSent).toBeTruthy();
    expect(fa.signup.emailSentDescription).toBeTruthy();
    expect(fa.signup.whyEmail).toBeTruthy();
    expect(fa.signup.whyTelegram).toBeTruthy();
    expect(en.signup.title).toBeTruthy();
    expect(en.signup.emailSubmit).toBeTruthy();
    expect(en.signup.emailSent).toBeTruthy();
  });

  it("contains verify page keys", () => {
    expect(fa.verify.verifying).toBeTruthy();
    expect(fa.verify.emailVerified).toBeTruthy();
    expect(fa.verify.linkingCodeInstruction).toBeTruthy();
    expect(fa.verify.openBot).toBeTruthy();
    expect(fa.verify.errorTitle).toBeTruthy();
    expect(fa.verify.errorExpired).toBeTruthy();
    expect(fa.verify.errorInvalid).toBeTruthy();
    expect(en.verify.emailVerified).toBeTruthy();
    expect(en.verify.openBot).toBeTruthy();
    expect(en.verify.errorTitle).toBeTruthy();
  });

  it("contains dashboard keys", () => {
    expect(fa.dashboard.title).toBeTruthy();
    expect(fa.dashboard.noSubmissions).toBeTruthy();
    expect(fa.dashboard.noVotes).toBeTruthy();
    expect(fa.dashboard.underReview).toBeTruthy();
    expect(fa.dashboard.disputeType).toBeTruthy();
    expect(en.dashboard.noSubmissions).toBeTruthy();
  });

  it("contains analytics keys", () => {
    expect(fa.analytics.clusters).toBeTruthy();
    expect(fa.analytics.topPolicies).toBeTruthy();
    expect(fa.analytics.evidence).toBeTruthy();
    expect(fa.analytics.noClusters).toBeTruthy();
    expect(fa.analytics.noCycles).toBeTruthy();
    expect(fa.analytics.verifyChain).toBeTruthy();
    expect(fa.analytics.chainValid).toBeTruthy();
    expect(en.analytics.noClusters).toBeTruthy();
    expect(en.analytics.verifyChain).toBeTruthy();
  });
});
