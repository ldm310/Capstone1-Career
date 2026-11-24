// 화면 정가운데에 도는 도넛과 "로딩 중" 문구를 보여준다.
// inline이면 화면 전체 대신 놓인 영역의 가운데에 표시한다.
export function LoadingSpinner({ inline = false }: { inline?: boolean }) {
  return (
    <div
      className={`loading-spinner ${inline ? "is-inline" : ""}`}
      role="status"
      aria-live="polite"
    >
      <span className="loading-ring" aria-hidden="true" />
      <p>로딩 중</p>
    </div>
  );
}
