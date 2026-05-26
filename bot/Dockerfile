FROM node:20-alpine

WORKDIR /app

COPY bot/package.json ./
RUN npm install

COPY bot/tsconfig.json ./
COPY bot/src ./src

RUN npm run build

CMD ["npm", "start"]