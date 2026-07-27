FROM node:20-alpine

WORKDIR /app

# 安装依赖
COPY package.json package-lock.json ./
RUN npm ci

# 复制源码
COPY . .

# Nuxt 3 开发模式（热重载）
EXPOSE 3000
CMD ["npm", "run", "dev"]
