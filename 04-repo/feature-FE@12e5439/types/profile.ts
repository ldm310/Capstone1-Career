// 마이페이지에서 수정하는 내 정보. 모든 항목은 선택 입력이다.
export interface Profile {
  education: string;
  school: string;
  major: string;
  career: string;
  location: string;
  github: string;
  intro: string;
}
export const emptyProfile: Profile = {
  education: "",
  school: "",
  major: "",
  career: "",
  location: "",
  github: "",
  intro: "",
};
export const educationOptions = [
  "고졸",
  "초대졸",
  "대졸(4년제)",
  "석사",
  "박사",
] as const;
export const careerOptions = [
  "신입",
  "경력 1~3년",
  "경력 3~5년",
  "경력 5년 이상",
] as const;
