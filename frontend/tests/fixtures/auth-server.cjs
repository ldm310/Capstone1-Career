/* eslint-disable @typescript-eslint/no-require-imports -- Isolated Node server fixture. */
const path=require('node:path');
const {mkdirSync,mkdtempSync,writeFileSync}=require('node:fs');
const root=path.resolve(__dirname,'../..');
mkdirSync(path.join(root,'work'),{recursive:true});
const directory=mkdtempSync(path.join(root,'work/auth-security-'));
writeFileSync(path.join(root,'work/auth-test-current.json'),JSON.stringify({directory}));
Object.assign(process.env,{
 CAREER_DATA_DIR:directory,CAREER_ACCOUNT_STORE:'sqlite',CAREER_PROFILE_DATABASE_URL:'',BACKEND_URL:'',
 KAKAO_REST_API_KEY:'isolated-test-client',KAKAO_CLIENT_SECRET:'isolated-test-secret',
 KAKAO_REDIRECT_URI:'http://127.0.0.1:3108/api/auth/kakao/callback',
 CAREER_PUBLIC_URL:'http://127.0.0.1:3108',CAREER_MAIL_TRANSPORT:'file',
 NAVER_CLIENT_ID:'isolated-naver-client',NAVER_CLIENT_SECRET:'isolated-naver-secret',NAVER_REDIRECT_URI:'http://127.0.0.1:3108/api/auth/naver/callback',
});
process.env.NODE_ENV='development';
require('./kakao-fetch.cjs');
process.chdir(root);
const app=require('next')({dev:true,dir:root,hostname:'127.0.0.1',port:3108});
app.prepare().then(()=>{
 const server=require('node:http').createServer(app.getRequestHandler());
 server.listen(3108,'127.0.0.1');
 const close=()=>{server.closeAllConnections();server.close();app.close().finally(()=>process.exit(0));};
 process.on('SIGTERM',close);process.on('SIGINT',close);
}).catch(error=>{console.error(error.name);process.exit(1);});
