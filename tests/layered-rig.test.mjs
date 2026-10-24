import test from 'node:test';
import assert from 'node:assert/strict';
import {projectPoint,StrandSpring,grid} from '../companion/avatar_web/layered-rig.js';

test('neutral projection preserves source pixels, including hair and neck',()=>{
  for(const type of ['hair','face','neck','body','earring'])for(const [x,y] of [[400,450],[632,600],[630,800],[950,1100]]){
    const point=projectPoint(x,y,{type,root:690,tip:1254},{},0,0,0);
    assert.ok(Math.abs(point[0]-x)<1e-9);assert.ok(Math.abs(point[1]-y)<1e-9);
  }
});

test('turns change nose/eye spacing and chin height while collar stays anchored',()=>{
  const face={type:'face'},nosePart={type:'nose',cx:632,cy:650},body={type:'body'};
  const distances=[];
  for(const angleX of [-12,12]){
    const nose=projectPoint(632,650,nosePart,{angleX});
    const l=projectPoint(532,595,face,{angleX}),r=projectPoint(732,595,face,{angleX});
    distances.push((nose[0]-l[0])-(r[0]-nose[0]));
  }
  assert.ok(distances[0]<-10&&distances[1]>10,distances);
  const up=projectPoint(632,800,face,{angleY:4}),down=projectPoint(632,800,face,{angleY:-4});
  assert.ok(down[1]-up[1]>20);
  assert.deepEqual(projectPoint(632,900,body,{angleX:12,angleY:4}),[632,900]);
});

test('all shared hair boundaries use the same projection and roots do not swing',()=>{
  const pose={angleX:12,angleY:4,angleZ:6};
  const a={type:'hair',root:690,tip:1254},b={...a};
  assert.deepEqual(projectPoint(400,690,a,pose,12),projectPoint(400,690,b,pose,-12));
  assert.ok(projectPoint(450,1100,a,pose,10)[0]>projectPoint(450,1100,a,pose,-10)[0]+15);
});

test('combined poses keep sampled triangle winding and finite vertices',()=>{
  const definitions=[
    [{type:'face'},[380,180,525,635]], [{type:'neck'},[540,750,200,130]],
    [{type:'hair',root:690,tip:1254},[0,165,1254,1089]], [{type:'body'},[0,780,1254,474]],
    [{type:'eye',component:'open',cx:529,cy:594,side:-1},[424,529,210,130]],
    [{type:'eye',component:'open',cx:740,cy:583,side:1},[635,518,210,130]],
    [{type:'brow',cx:733,cy:531,side:1},[643,501,180,60]],
    [{type:'nose',cx:633,cy:660},[595,610,78,100]],
    [{type:'mouth',cx:635,cy:720},[565,675,140,90]],
    [{type:'hair',part:'bang',side:0,root:310,tip:680},[530,235,205,455]],
    [{type:'hair',part:'side',side:-1,root:315,tip:730},[345,220,265,560]],
  ];
  for(const [layer,bounds] of definitions){
    const mesh=grid(bounds,12);
    for(const angleX of [-12,12])for(const angleY of [-4,4])for(const angleZ of [-8,8]){
      const points=mesh.points.map(([x,y])=>projectPoint(x,y,layer,{angleX,angleY,angleZ},5));
      assert.ok(points.flat().every(Number.isFinite));
      for(let i=0;i<mesh.indices.length;i+=3){
        const [a,b,c]=Array.from(mesh.indices.slice(i,i+3),n=>points[n]);
        const area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
        assert.ok(area>0,`${layer.type} folded at ${i}: ${area}`);
      }
    }
  }
});

test('far eye narrows and near eye widens, with the roles reversed on the other turn',()=>{
  const eyes=[{type:'eye',cx:529,cy:594,side:-1},{type:'eye',cx:740,cy:583,side:1}];
  const width=(eye,angleX)=>projectPoint(eye.cx+55,eye.cy,eye,{angleX})[0]-projectPoint(eye.cx-55,eye.cy,eye,{angleX})[0];
  for(const angleX of [-12,12]){
    const near=angleX>0?eyes[0]:eyes[1],far=angleX>0?eyes[1]:eyes[0];
    assert.ok(width(near,angleX)>width(near,0));
    assert.ok(width(far,angleX)<width(far,0)*.85);
  }
});

test('eye closure and brow movement deform their own parts without dragging the face',()=>{
  const eye={type:'eye',component:'open',cx:529,cy:594,side:-1};
  const height=eyeOpen=>projectPoint(529,620,eye,{eyeOpen})[1]-projectPoint(529,565,eye,{eyeOpen})[1];
  assert.ok(height(.05)<height(1)*.4);
  const brow={type:'brow',cx:733,cy:531,side:1};
  assert.ok(projectPoint(733,531,brow,{browY:.25})[1]<525);
  assert.deepEqual(projectPoint(632,720,{type:'face'},{browY:.25}),[632,720]);
});

test('cropped bust baseline stays horizontal during combined turns and secondary movement',()=>{
  const pose={angleX:12,angleY:-4,angleZ:8,bodyAngleX:1.5,bodyAngleZ:1.2};
  for(const type of ['hair','body','face'])for(const x of [0,160,632,1100,1254]){
    assert.deepEqual(projectPoint(x,1254,{type,root:690,tip:1254},pose,12,1,1),[x,1254]);
  }
  assert.notDeepEqual(projectPoint(400,1000,{type:'body'},pose),[400,1000]);
});

test('strand solver is stable across redraw jitter and returns to rest',()=>{
  const spring=new StrandSpring();let maximum=0;
  for(let i=0;i<2400;i++){
    const x=spring.update([.0166667,.000001,.0333334,0][i%4],Math.sin(i/150)*12);
    assert.ok(Number.isFinite(x)&&Number.isFinite(spring.v));maximum=Math.max(maximum,Math.abs(x));
  }
  assert.ok(maximum>5&&maximum<13);
  const x=spring.x,v=spring.v;spring.update(0,20);assert.equal(spring.x,x);assert.equal(spring.v,v);
  for(let i=0;i<240;i++)spring.update(1/60,0);
  assert.ok(Math.abs(spring.x)<1e-8&&Math.abs(spring.v)<1e-7);
});

test('exact spring has equivalent timing at 30, 60 and 120 Hz',()=>{
  const result=[30,60,120].map(fps=>{const s=new StrandSpring();for(let i=0;i<fps;i++)s.update(1/fps,10);return s.x;});
  assert.ok(Math.max(...result)-Math.min(...result)<1e-10);
});
