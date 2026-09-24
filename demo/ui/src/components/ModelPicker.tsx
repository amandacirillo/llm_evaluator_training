interface Props {
  label: string;
  value: string;
  options: string[];
  /** Models chosen in the other pickers — disabled here to prevent duplicates. */
  taken: string[];
  required?: boolean;
  onChange: (value: string) => void;
}

export default function ModelPicker({
  label,
  value,
  options,
  taken,
  required,
  onChange,
}: Props) {
  return (
    <label className="block">
      <span className="text-xs text-ink-muted">
        {label}
        {required ? "" : " (optional)"}
      </span>
      <select
        className="mt-1 w-full rounded border border-border bg-surface px-3 py-2 text-sm text-ink focus:border-accent-strong focus:outline-none focus:ring-2 focus:ring-accent-soft"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{required ? "Select a model…" : "None"}</option>
        {options.map((m) => (
          <option key={m} value={m} disabled={m !== value && taken.includes(m)}>
            {m}
          </option>
        ))}
      </select>
    </label>
  );
}
