const realFetch=globalThis.fetch;
globalThis.fetch=async(input,init)=>{
 const url=typeof input==='string'?input:input instanceof URL?input.href:input.url;
 if(url==='https://kauth.kakao.com/oauth/token')return Response.json({access_token:new URLSearchParams(init.body).get('code')});
 if(url==='https://kapi.kakao.com/v2/user/me') {
  const auth=new Headers(init.headers).get('authorization')||'';
  const identity=JSON.parse(Buffer.from(auth.slice('Bearer '.length),'base64url').toString('utf8'));
  return Response.json({id:identity.subject,kakao_account:{is_email_valid:identity.verified!==false,is_email_verified:identity.verified!==false,email:identity.email,profile:{nickname:'카카오 검증'}}});
 }
 return realFetch(input,init);
};
