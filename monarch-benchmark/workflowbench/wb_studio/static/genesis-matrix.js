/* Perspective ASCII scenes. Time is seconds; frames depend only on phase, time and size. */
(function () {
  'use strict';
  const TAU=Math.PI*2, cache=new Map();
  const ramp='.,:;irsXA253hMHGS#9B&@';
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const normalize=v=>{const n=Math.hypot(...v)||1;return v.map(x=>x/n);};
  const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  function rotation(ax,ay,az) {
    const sx=Math.sin(ax),cx=Math.cos(ax),sy=Math.sin(ay),cy=Math.cos(ay),sz=Math.sin(az),cz=Math.cos(az);
    return [cy*cz,sx*sy*cz-cx*sz,cx*sy*cz+sx*sz,cy*sz,sx*sy*sz+cx*cz,cx*sy*sz-sx*cz,-sy,sx*cy,cx*cy];
  }
  const transform=(p,m)=>[m[0]*p[0]+m[1]*p[1]+m[2]*p[2],m[3]*p[0]+m[4]*p[1]+m[5]*p[2],m[6]*p[0]+m[7]*p[1]+m[8]*p[2]];
  function geometry(phase) {
    if(cache.has(phase))return cache.get(phase);
    const points=[];
    function point(p,n,glow=0) {points.push(...p,...n,glow);}
    function sphere(center,radii,folded=false,glow=0,quality=1) {
      const nu=Math.ceil(116*quality),nv=Math.ceil(70*quality);
      function position(u,v) {
        const ridges=folded ? 1+.075*Math.sin(13*v+2.4*Math.sin(5*u))+.043*Math.sin(19*u+4*Math.cos(6*v))*Math.sin(v) : 1;
        const sv=Math.sin(v),cv=Math.cos(v);
        return [center[0]+radii[0]*ridges*sv*Math.cos(u),center[1]+radii[1]*ridges*cv,center[2]+radii[2]*ridges*sv*Math.sin(u)];
      }
      for(let j=1;j<nv;j++)for(let i=0;i<nu;i++) {
        const u=i/nu*TAU,v=j/nv*Math.PI,p=position(u,v),pu=position(u+.002,v),pv=position(u,v+.002);
        const n=normalize(cross(pu.map((x,k)=>x-p[k]),pv.map((x,k)=>x-p[k])));
        point(p,n,glow);
      }
    }
    function tube(a,b,r=.018,glow=.1) {
      const axis=normalize(b.map((x,k)=>x-a[k]));
      const side=normalize(cross(axis,Math.abs(axis[1])<.9?[0,1,0]:[1,0,0])),up=cross(axis,side);
      const count=Math.ceil(Math.hypot(...b.map((x,k)=>x-a[k]))*80);
      for(let i=0;i<=count;i++)for(let j=0;j<10;j++) {
        const t=i/Math.max(1,count),angle=j/10*TAU,n=side.map((x,k)=>x*Math.cos(angle)+up[k]*Math.sin(angle));
        point(a.map((x,k)=>x+(b[k]-x)*t+n[k]*r),n,glow);
      }
    }
    function torus(radius,thickness,angles=[0,0,0],center=[0,0,0],glow=.1) {
      const m=rotation(...angles);
      for(let i=0;i<260;i++)for(let j=0;j<10;j++) {
        const u=i/260*TAU,v=j/10*TAU,n=[Math.cos(v)*Math.cos(u),Math.sin(v),Math.cos(v)*Math.sin(u)];
        const p=transform([(radius+thickness*Math.cos(v))*Math.cos(u),thickness*Math.sin(v),(radius+thickness*Math.cos(v))*Math.sin(u)],m);
        point(p.map((x,k)=>x+center[k]),transform(n,m),glow);
      }
    }
    function box(center,half,angles=[0,0,0],wire=false,glow=0) {
      const m=rotation(...angles),world=p=>transform(p,m).map((x,k)=>x+center[k]);
      if(wire) {
        const corners=[];
        for(let i=0;i<8;i++)corners.push(world(half.map((x,k)=>x*((i>>k)&1?1:-1))));
        for(let i=0;i<8;i++)for(let j=0;j<3;j++)if(!(i&(1<<j)))tube(corners[i],corners[i|(1<<j)],.018,glow);
        return;
      }
      for(let axis=0;axis<3;axis++)for(const sign of [-1,1]) {
        const u=(axis+1)%3,v=(axis+2)%3,n=[0,0,0];n[axis]=sign;
        const nu=Math.ceil(half[u]*110),nv=Math.ceil(half[v]*110);
        for(let i=0;i<=nu;i++)for(let j=0;j<=nv;j++) {
          const p=[0,0,0];p[axis]=half[axis]*sign;p[u]=(i/nu*2-1)*half[u];p[v]=(j/nv*2-1)*half[v];
          point(world(p),transform(n,m),glow);
        }
      }
    }
    function prism(polygon,depth,glow=0) {
      const xs=polygon.map(p=>p[0]),ys=polygon.map(p=>p[1]),minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);
      function inside(x,y) {
        let hit=false;
        for(let i=0,j=polygon.length-1;i<polygon.length;j=i++) {
          const a=polygon[i],b=polygon[j];
          if((a[1]>y)!==(b[1]>y) && x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])hit=!hit;
        }
        return hit;
      }
      for(let y=miny;y<=maxy;y+=.018)for(let x=minx;x<=maxx;x+=.018)if(inside(x,y)) {
        point([x,y,depth],[0,0,1],glow);point([x,y,-depth],[0,0,-1],glow);
      }
      for(let i=0;i<polygon.length;i++) {
        const a=polygon[i],b=polygon[(i+1)%polygon.length],length=Math.hypot(b[0]-a[0],b[1]-a[1]),steps=Math.ceil(length*70),normal=normalize([b[1]-a[1],a[0]-b[0],0]);
        for(let j=0;j<=steps;j++)for(let z=-depth;z<=depth;z+=.018)point([a[0]+(b[0]-a[0])*j/steps,a[1]+(b[1]-a[1])*j/steps,z],normal,glow);
      }
    }
    if(phase==='thinking') {
      // A real medial fissure, folded cortex, asymmetric lobes and brain stem.
      sphere([-.59,.16,0],[.57,1.05,.78],true,0,1.5);
      sphere([.59,.18,0],[.57,1.02,.79],true,0,1.5);
      sphere([0,-.95,-.23],[.25,.38,.28],true,0,.55);
      tube([0,-1.05,-.24],[.10,-1.49,-.19],.16,0);
    } else if(phase==='research') {
      sphere([0,0,0],[.88,.88,.88],false,-.08);
      for(const angle of [[0,0,0],[Math.PI/2,0,0],[0,0,Math.PI/2]])torus(.91,.012,angle,[0,0,0],.3);
      torus(1.47,.024,[.48,.3,.38],[0,0,0],.3);
      torus(1.34,.017,[-.72,.1,-.55],[0,0,0],.14);
      sphere([1.42,.21,.27],[.13,.13,.13],false,.4,.4);
      sphere([-.88,.94,-.50],[.09,.09,.09],false,.4,.35);
    } else if(phase==='architecture') {
      const nodes=[[0,.13,.15],[-1.10,.77,.08],[.85,.91,-.47],[1.32,-.09,.18],[.70,-1.02,.35],[-.65,-1.0,-.43],[-1.37,-.25,.13],[.2,.15,-1.16]];
      for(let i=1;i<nodes.length;i++)tube(nodes[0],nodes[i],.02,.2);
      for(const [a,b] of [[1,2],[2,3],[3,4],[4,5],[5,6],[6,1],[1,7],[4,7]])tube(nodes[a],nodes[b],.01,-.12);
      nodes.forEach((p,i)=>sphere(p,[i?.13:.24,i?.13:.24,i?.13:.24],false,i?.24:.1,.55));
    } else if(phase==='configuration') {
      box([0,0,0],[1.02,1.02,1.02],[.14,.10,0],true,.18);
      box([0,0,0],[.69,.69,.69],[.50,.49,.32],true,.35);
      box([0,0,0],[.29,.29,.29],[.50,.49,.32],false,.08);
      sphere([1.12,1.0,-.7],[.065,.065,.065],false,.5,.3);
    } else if(phase==='execution') {
      prism([[.27,1.46],[-.77,.04],[-.13,.04],[-.44,-1.48],[.86,.35],[.12,.35],[.67,1.46]],.23,.02);
      tube([-1.30,.91,-.30],[-.99,.58,-.3],.013,.36);
      tube([1.02,-.43,-.30],[1.32,-.75,-.30],.013,.36);
      tube([.96,1.10,-.13],[1.21,1.4,-.13],.012,.23);
    } else if(phase==='warning') {
      prism([[0,1.36],[-1.37,-1.08],[1.37,-1.08]],.14,-.10);
      box([0,.22,.18],[.105,.46,.06],[0,0,0],false,.53);
      sphere([0,-.57,.23],[.13,.13,.045],false,.55,.4);
    } else {
      box([0,0,0],[.81,1.20,.23],[0,0,0],false,-.05);
      for(const y of [.70,.34,-.02])box([-.06,y,.27],[.50,.025,.045],[0,0,0],false,.45);
      box([-.27,-.39,.27],[.28,.025,.045],[0,0,0],false,.45);
      box([.24,-.70,.27],[.21,.10,.04],[0,0,0],false,.25);
    }
    const result=new Float32Array(points);cache.set(phase,result);return result;
  }
  function rain(time,width,height) {
    const out=Array(width*height).fill(' ');
    for(let x=2;x<width;x+=5) {
      let seed=Math.imul(x^2654435769,2246822507)>>>0;seed=Math.imul(seed^(seed>>>13),3266489909)>>>0;
      const speed=3+seed%5,head=((Math.floor(time*speed)+seed)%(height+12))-6;
      for(let k=0;k<8;k++) {
        const y=head-k;if(y<0||y>=height)continue;
        const digit=((seed+k*37+Math.floor(time*2))>>>0)%10;
        out[y*width+x]=k===0 ? String(digit) : k<3 ? (digit%2?'1':'0') : k<5 ? ':' : '.';
      }
    }
    return out;
  }
  function layers(phase='thinking',time=0,width=96,height=38) {
    width=clamp(Math.round(Number(width)||96),32,160);height=clamp(Math.round(Number(height)||38),16,70);time=Number.isFinite(Number(time))?Number(time):0;
    const known=['thinking','research','architecture','configuration','execution','result','warning'];if(!known.includes(phase))phase='thinking';
    const points=geometry(phase),depth=new Float32Array(width*height).fill(-Infinity),body=Array(width*height).fill(' '),back=rain(time,width,height);
    const angle=phase==='execution'?.40+Math.sin(time*.48)*.42:phase==='warning'?.24+Math.sin(time*.32)*.24:phase==='result'?.35+Math.sin(time*.22)*.26:time*(phase==='thinking'?.38:.29);
    const tilt=phase==='thinking'?.12+Math.sin(time*.28)*.1:phase==='architecture'?.24:phase==='configuration'?.30:-.12;
    const matrix=rotation(tilt,angle,phase==='execution'?-.10:Math.sin(time*.15)*.025);
    const scale=Math.min(width*1.42,height*3.14),camera=5.7;
    // The light stays in viewer space. A turning surface changes its illumination.
    const lx=-.37,ly=.57,lz=.73;
    for(let i=0;i<points.length;i+=7) {
      const x=matrix[0]*points[i]+matrix[1]*points[i+1]+matrix[2]*points[i+2];
      const y=matrix[3]*points[i]+matrix[4]*points[i+1]+matrix[5]*points[i+2];
      const z=matrix[6]*points[i]+matrix[7]*points[i+1]+matrix[8]*points[i+2];
      const nx=matrix[0]*points[i+3]+matrix[1]*points[i+4]+matrix[2]*points[i+5];
      const ny=matrix[3]*points[i+3]+matrix[4]*points[i+4]+matrix[5]*points[i+5];
      const nz=matrix[6]*points[i+3]+matrix[7]*points[i+4]+matrix[8]*points[i+5];
      if(nz<-.24)continue;
      const perspective=scale/(camera-z),sx=Math.round(width/2+x*perspective),sy=Math.round(height/2-y*perspective*.49);
      if(sx<1||sx>=width-1||sy<1||sy>=height-1)continue;
      const index=sy*width+sx;if(z<=depth[index])continue;
      depth[index]=z;
      const diffuse=Math.max(0,nx*lx+ny*ly+nz*lz),rim=Math.pow(1-Math.abs(nz),3)*.11;
      const brightness=clamp(.12+diffuse*.76+rim+points[i+6],.055,1);
      body[index]=ramp[Math.round(brightness*(ramp.length-1))];
    }
    // Foreground owns its silhouette; background is left intact only in empty space.
    const merged=body.map((char,index)=>char===' '?back[index]:char);
    function lines(chars) {const result=[];for(let y=0;y<height;y++)result.push(chars.slice(y*width,(y+1)*width).join(''));return result.join('\n');}
    return {body:lines(body),rain:lines(back.map((char,i)=>body[i]===' '?char:' ')),frame:lines(merged)};
  }
  window.GenesisMatrix={frame:(phase,time,width=96,height=38)=>layers(phase,time,width,height).frame,layers};
}());
