import { skillCategories } from "@/lib/skill-categories";
import type { SavedPostingLevel } from "@/types/posting-level";
import { RadarPoint } from "./radar-point";

export function SavedLevelRadar({ levels }: { levels: SavedPostingLevel[] }) {
  const axes = skillCategories.flatMap((category) => {
    const items = levels.filter((row) =>
      row.categoryCodes.includes(category.code),
    );
    if (!items.length) return [];
    const references = items.filter((row) => row.referenceScore !== null);
    return [
      {
        ...category,
        count: items.length,
        mine: items.reduce((sum, row) => sum + row.score, 0) / items.length,
        reference:
          references.length === items.length
            ? references.reduce((sum, row) => sum + row.referenceScore!, 0) /
              references.length
            : null,
      },
    ];
  });
  const demo = levels.some((row) => row.evaluationKind === "DEMO");
  const kinds = new Set(levels.map((row) => row.referenceKind));
  const hasReference =
    axes.every((axis) => axis.reference !== null) && kinds.size === 1;
  const referenceLabel = kinds.has("SYNTHETIC_APPLICANTS")
    ? "경쟁자 평균 (더미)"
    : kinds.has("VERIFIED_APPLICANTS")
      ? "경쟁자 평균"
      : "공고 기준";
  const point = (index: number, radius: number) => {
    const angle = (index * 2 * Math.PI) / axes.length - Math.PI / 2;
    return {
      x: 260 + Math.cos(angle) * radius,
      y: 200 + Math.sin(angle) * radius,
    };
  };
  const polygon = (value: (axis: (typeof axes)[number]) => number) =>
    axes
      .map((axis, index) => {
        const p = point(index, (value(axis) / 100) * 118);
        return `${p.x},${p.y}`;
      })
      .join(" ");
  const description = axes
    .map(
      (axis) =>
        `${axis.name}: 내 LV ${axis.mine.toFixed(1)}${hasReference ? `, ${referenceLabel} LV ${axis.reference!.toFixed(1)}` : ""}`,
    )
    .join(". ");
  return (
    <section
      className="personal-radar-card saved-level-radar"
      aria-label="공고별 LV 비교"
    >
      <header>
        <h4>공고별 LV 비교</h4>
        <p>카테고리별 역량 문장 LV 평균, 0–100</p>
      </header>
      <div className="saved-level-legend">
        {hasReference && (
          <span>
            <i className="reference" />
            {referenceLabel}
          </span>
        )}
        <span>
          <i className="mine" />내 LV{demo ? " (더미)" : ""}
        </span>
      </div>
      {axes.length >= 3 ? (
        <svg
          viewBox="0 0 520 400"
          role="group"
          aria-label={description}
          data-testid="saved-level-radar"
        >
          <title>공고별 LV 비교</title>
          <desc>{description}</desc>
          {[20, 40, 60, 80, 100]
            .map((tick) => (
              <polygon
                key={tick}
                points={polygon(() => tick)}
                fill={tick === 100 ? "#f7f9ff" : "none"}
                stroke="#dce4ef"
              />
            ))
            .reverse()}
          {axes.map((axis, index) => {
            const edge = point(index, 118),
              label = point(index, 159);
            return (
              <g key={axis.code}>
                <line
                  x1="260"
                  y1="200"
                  x2={edge.x}
                  y2={edge.y}
                  stroke="#e0e7ef"
                />
                <text
                  x={label.x}
                  y={label.y}
                  textAnchor={
                    Math.abs(label.x - 260) < 10
                      ? "middle"
                      : label.x > 260
                        ? "start"
                        : "end"
                  }
                  fontSize="11"
                  fill="#43566d"
                >
                  {axis.label.map((line, i) => (
                    <tspan key={line} x={label.x} dy={i ? 14 : 0}>
                      {line.replaceAll("·", ", ")}
                    </tspan>
                  ))}
                </text>
              </g>
            );
          })}
          {[20, 40, 60, 80, 100].map((tick) => (
            <text
              key={tick}
              x="266"
              y={203 - (tick / 100) * 118}
              fontSize="9"
              fill="#536278"
            >
              {tick}
            </text>
          ))}
          {hasReference && (
            <polygon
              data-series="reference"
              points={polygon((axis) => axis.reference!)}
              fill="#3973eb"
              fillOpacity=".14"
              stroke="#3973eb"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
          )}
          <polygon
            data-series="mine"
            points={polygon((axis) => axis.mine)}
            fill="#55ae54"
            fillOpacity=".23"
            stroke="#479b45"
            strokeWidth="2.5"
            strokeLinejoin="round"
          />
          {axes.flatMap((axis, index) =>
            [
              ...(hasReference
                ? [
                    {
                      kind: "reference",
                      score: axis.reference!,
                      color: "#3973eb",
                    },
                  ]
                : []),
              { kind: "mine", score: axis.mine, color: "#479b45" },
            ].map((series) => {
              const p = point(index, (series.score / 100) * 118);
              return (
                <RadarPoint
                  key={`${axis.code}-${series.kind}`}
                  kind={series.kind}
                  x={p.x}
                  y={p.y}
                  color={series.color}
                  category={axis.name.replaceAll("·", ", ")}
                  series={series.kind === "mine" ? "내" : referenceLabel}
                  score={series.score}
                />
              );
            }),
          )}
        </svg>
      ) : (
        <p className="personal-comparison-note">
          {axes
            .map((axis) => `${axis.name} LV ${axis.mine.toFixed(1)}`)
            .join(",  ")}
        </p>
      )}
      <p className="personal-comparison-note">
        중심 0, 바깥선 100, 점에 마우스를 올리거나 선택하면 LV 표시
      </p>
    </section>
  );
}
