"use client";

export function ListPagination({
  total,
  offset,
  pageSize,
  loading = false,
  label,
  onChange,
}: {
  total: number;
  offset: number;
  pageSize: number;
  loading?: boolean;
  label: string;
  onChange: (offset: number) => void;
}) {
  const pages = Math.ceil(total / pageSize);
  const page = Math.floor(offset / pageSize) + 1;
  const numbers = Array.from({ length: pages }, (_, i) => i + 1).filter(
    (number) =>
      number === 1 || number === pages || Math.abs(number - page) <= 1,
  );
  return (
    <nav className="list-pagination" aria-label={label} aria-busy={loading}>
      <p className="list-pagination-summary" role="status">
        총 <strong>{total.toLocaleString("ko-KR")}</strong>개
        {total > 0 &&
          `, ${offset + 1}–${Math.min(offset + pageSize, total)}개 표시`}
      </p>
      {pages > 0 && (
        <div className="list-pagination-controls">
          <button
            type="button"
            disabled={loading || page <= 1}
            onClick={() => onChange(offset - pageSize)}
          >
            이전
          </button>
          <div className="list-pagination-numbers">
            {numbers.map((number, index) => (
              <span key={number}>
                {index > 0 && number - numbers[index - 1] > 1 && (
                  <span className="list-pagination-gap" aria-hidden="true">
                    …
                  </span>
                )}
                <button
                  type="button"
                  aria-label={`${number}페이지로 이동`}
                  aria-current={number === page ? "page" : undefined}
                  disabled={loading || number === page}
                  onClick={() => onChange((number - 1) * pageSize)}
                >
                  {number}
                </button>
              </span>
            ))}
          </div>
          <span className="list-pagination-position">
            {page} / {pages} 페이지
          </span>
          <button
            type="button"
            disabled={loading || page >= pages}
            onClick={() => onChange(offset + pageSize)}
          >
            다음
          </button>
        </div>
      )}
    </nav>
  );
}
