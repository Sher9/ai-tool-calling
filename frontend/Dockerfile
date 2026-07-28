# 前端 Vite 开发服务器镜像
FROM node:20-alpine

WORKDIR /app

# 先拷贝依赖清单以利用层缓存
COPY package.json ./
RUN npm install --registry=https://registry.npmmirror.com

# 拷贝源码
COPY . .

EXPOSE 5173

# 监听 0.0.0.0，便于容器外部访问；代理目标通过 VITE_PROXY_TARGET 注入
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
