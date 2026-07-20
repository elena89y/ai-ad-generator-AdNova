# frontend-next (Next.js 16) — v6 T5 초안: 한의정 (프론트 도메인: 정봄 — 막바지 합의, PR 기록)
# 단순 2-스테이지: 빌드 → npm start. (standalone output 전환은 이미지 슬리밍 후속 — next.config 수정 필요)
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["npm", "start"]
