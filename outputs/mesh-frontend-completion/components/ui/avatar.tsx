import { cn } from "@/lib/utils/cn";
import { initials } from "@/lib/utils/format";

const palettes = [
  "from-[#635BFF] to-[#A78BFA]",
  "from-[#00C9A7] to-[#67E8F9]",
  "from-[#38BDF8] to-[#635BFF]",
  "from-[#FF6B8A] to-[#FFB547]",
  "from-[#A78BFA] to-[#FF6B8A]",
  "from-[#4F46E5] to-[#38BDF8]",
];

function hash(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

export function Avatar({
  name,
  src,
  size = 36,
  className,
}: {
  name: string;
  src?: string;
  size?: number;
  className?: string;
}) {
  return (
    <span
      aria-label={name}
      role="img"
      style={{ width: size, height: size, fontSize: Math.max(10, size * 0.36), ...(src?.startsWith("data:image/") ? { backgroundImage: `url(${src})`, backgroundSize: "cover", backgroundPosition: "center" } : {}) }}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br font-semibold text-white ring-2 ring-white",
        palettes[hash(name) % palettes.length],
        className
      )}
    >
      {src ? <span className="sr-only">{initials(name)}</span> : initials(name)}
    </span>
  );
}

export function AvatarStack({ names, size = 28, max = 4 }: { names: string[]; size?: number; max?: number }) {
  const shown = names.slice(0, max);
  const rest = names.length - shown.length;
  return (
    <div className="flex items-center -space-x-2">
      {shown.map((n) => (
        <Avatar key={n} name={n} size={size} />
      ))}
      {rest > 0 && (
        <span
          style={{ width: size, height: size }}
          className="inline-flex items-center justify-center rounded-full bg-[#eef1fa] text-[10px] font-semibold text-ink-2 ring-2 ring-white"
        >
          +{rest}
        </span>
      )}
    </div>
  );
}
