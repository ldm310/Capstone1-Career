"use client";
import { useId, useState } from "react";
import { Check, Plus, Upload, Link2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useCareer } from "@/components/shared/career-provider";
import { SourceIcon } from "@/components/skills/evidence-badge";
import type { EvidenceSource } from "@/types/career";
const sources: {
  id: EvidenceSource;
  name: string;
  description: string;
  label: string;
}[] = [
  {
    id: "github",
    name: "GitHub",
    description: "실제 프로젝트 구현 역량 근거",
    label: "체험 연결",
  },
  {
    id: "cv",
    name: "이력서",
    description: "프로젝트 및 경험 역량 근거",
    label: "파일 선택",
  },
  {
    id: "notion",
    name: "Notion",
    description: "학습 및 기술 정리 역량 근거",
    label: "체험 연결",
  },
  {
    id: "certificate",
    name: "자격증",
    description: "공식 자격 역량 근거",
    label: "추가",
  },
];
export function SourceConnector() {
  const { profile, connect, disconnect } = useCareer();
  const [certificateOpen, setCertificateOpen] = useState(false);
  const [certificate, setCertificate] = useState("");
  const [error, setError] = useState("");
  const fileId = useId();
  return (
    <>
      <div className="source-connectors">
        {sources.map((source) => {
          const connection = profile.connections.find(
            (c) => c.source === source.id,
          );
          return (
            <div
              className={`source-connector ${connection?.connected ? "connected" : ""}`}
              key={source.id}
            >
              <span className="connector-icon">
                <SourceIcon source={source.id} size={23} />
              </span>
              <div className="connector-copy">
                <strong>{source.name}</strong>
                <p>{source.description}</p>
                {connection?.connected && <small>{connection.label}</small>}
              </div>
              {connection?.connected ? (
                <div className="connected-actions">
                  <span>
                    <Check size={13} />
                    준비됨
                  </span>
                  <button
                    aria-label={`${source.name} 연결 해제`}
                    className="icon-button"
                    onClick={() => disconnect(source.id)}
                  >
                    <X size={13} />
                  </button>
                </div>
              ) : source.id === "cv" ? (
                <>
                  <label className="upload-button" htmlFor={fileId}>
                    <Upload size={13} />
                    파일 선택
                  </label>
                  <input
                    id={fileId}
                    type="file"
                    className="sr-only"
                    accept=".pdf,.doc,.docx"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      if (!/\.(pdf|docx?)$/i.test(file.name)) {
                        setError("PDF 또는 Word 파일을 선택하세요.");
                        return;
                      }
                      if (file.size > 10 * 1024 * 1024) {
                        setError("10MB 이하의 파일을 선택하세요.");
                        return;
                      }
                      setError("");
                      connect("cv", file.name);
                      e.target.value = "";
                    }}
                  />
                </>
              ) : (
                <Button
                  variant="outline"
                  onClick={() =>
                    source.id === "certificate"
                      ? setCertificateOpen(true)
                      : connect(source.id, `${source.name} 체험 자료`)
                  }
                >
                  {source.id === "certificate" ? (
                    <Plus size={13} />
                  ) : (
                    <Link2 size={13} />
                  )}{" "}
                  {source.label}
                </Button>
              )}
            </div>
          );
        })}
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <a className="source-real-link" href="/my-skills">실제 자료 분석: GitHub 코드·Notion 학습 기록·이력서에서 기술과 원문을 확인하기 →</a>
      <p className="demo-note">
        파일명만 이 브라우저에 저장합니다. 파일 전송·내용 분석·실제 OAuth 연결은
        수행하지 않습니다.
      </p>
      <Dialog open={certificateOpen} onOpenChange={setCertificateOpen}>
        <DialogContent>
          <DialogTitle>자격증 추가</DialogTitle>
          <DialogDescription>
            자격증 이름을 체험 연결 정보로 저장합니다. 실제 자격 검증은 수행하지
            않습니다.
          </DialogDescription>
          <form
            className="form-grid"
            onSubmit={(e) => {
              e.preventDefault();
              if (!certificate.trim()) return;
              connect("certificate", certificate.trim());
              setCertificateOpen(false);
              setCertificate("");
            }}
          >
            <label className="field-label">
              자격증 이름
              <input
                required
                maxLength={100}
                className="form-input"
                placeholder="예: SQLD"
                value={certificate}
                onChange={(e) => setCertificate(e.target.value)}
              />
            </label>
            <Button type="submit">자격증 추가하기</Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
