#!/usr/bin/env bash
# EC2 에 스테이징 웹 주소를 만든다(처음 한 번, 여러 번 돌려도 안전). 운영(3000번, career-web)은 건드리지 않는다.
#   https://staging.<HOST> → 127.0.0.1:3001 (nginx + Let's Encrypt 인증서)
# 스테이징 서비스 자체는 deploy.sh 가 처음 배포할 때 만든다(웹 코드가 develop 에 들어온 뒤).
# 사용: ssh ubuntu@<EC2> 'bash -s' < deploy/web/setup_ec2.sh
set -euo pipefail

HOST=${HOST:-15-164-137-78.sslip.io}
STAGING=staging.$HOST
site=/etc/nginx/sites-available/career-web-staging

mkdir -p "$HOME/career-data-staging"
if [ ! -f "$site" ]; then
  sudo tee "$site" >/dev/null <<EOF
# 스테이징(develop) — deploy/web/setup_ec2.sh 가 만듦, certbot 이 https 를 붙임
server {
    listen 80;
    listen [::]:80;
    server_name $STAGING;
    client_max_body_size 12m;
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
  sudo ln -sfn "$site" /etc/nginx/sites-enabled/career-web-staging
  sudo nginx -t
  sudo systemctl reload nginx
fi
if ! sudo test -d "/etc/letsencrypt/live/$STAGING"; then
  sudo certbot --nginx -d "$STAGING" --non-interactive --agree-tos --redirect --register-unsafely-without-email
fi
echo "스테이징 주소 준비됨: https://$STAGING (웹 코드가 develop 에 들어오면 deploy.sh 가 3001번에 띄움)"
