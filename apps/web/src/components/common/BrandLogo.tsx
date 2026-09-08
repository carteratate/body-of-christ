import Image from "next/image";

export function BrandLogo({ className = "" }: { className?: string }) {
  return (
    <div className={`shrink-0 ${className}`} aria-hidden="true">
      <Image
        src="/query-logo-classical-serif-dark.png"
        alt=""
        width={256}
        height={256}
        className="brand-logo-dark h-full w-full object-contain"
        priority
      />
      <Image
        src="/query-logo-classical-serif-light.png"
        alt=""
        width={256}
        height={256}
        className="brand-logo-light h-full w-full object-contain"
        priority
      />
    </div>
  );
}
