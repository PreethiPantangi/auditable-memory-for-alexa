export default function AlexaPlusLogo() {
  return (
    <div className="flex flex-col items-start">
      <div className="relative inline-block">
        <div className="text-[30px] font-bold leading-none tracking-tight text-slate-900">
          <span className="lowercase">alexa</span>
          <span className="text-blue-600">+</span>
        </div>

        {/* smile underline */}
        <svg
          viewBox="0 0 120 26"
          className="mt-1 h-5 w-23"
          aria-hidden="true"
        >
          <path
            d="M8 8 C 28 25, 72 25, 104 10"
            fill="none"
            stroke="#2563eb"
            strokeWidth="5"
            strokeLinecap="round"
          />
          <path
            d="M98 8 L108 10 L101 18"
            fill="none"
            stroke="#2563eb"
            strokeWidth="5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      <p className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        Alexa+ companion demo
      </p>
    </div>
  );
}