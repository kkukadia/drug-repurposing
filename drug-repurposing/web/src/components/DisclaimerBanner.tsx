export const DISCLAIMER_TEXT =
  "Not medical advice. These are computational hypotheses for researchers, not treatment recommendations.";

export function DisclaimerBanner({ text }: { text?: string }) {
  return (
    <div role="alert" className="banner">
      <strong>Not medical advice.</strong> {text ?? DISCLAIMER_TEXT}
    </div>
  );
}
