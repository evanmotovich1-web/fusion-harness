export default async ({ project }) => {
  const p = await project({dir:"ad", size:"720x1280", fps:30, background:"#103F3D"});
  const footage = await p.add("/home/user/source.mp4");
  p.cut(footage, {from:0, dur:7, at:0, fit:"cover"});
  p.compose(<frame width={720} height={1280} layout="none">
    <rect x={52} y={65} width={370} height={54} radius={27} fill="#FFF9ED"/>
    <text x={74} y={79} width={325} height={30} fontFamily="Inter" fontSize={21} fontWeight={700} color="#103F3D">SPECIALISTS IN CARE</text>
  </frame>, {at:0,dur:7,name:"Brand"});
  p.compose(<frame width={720} height={1280} layout="none" motion={{enter:{from:{opacity:0,y:12},duration:0.2}}}>
    <rect x={40} y={948} width={640} height={218} radius={24} fill="#FFF9ED"/>
    <text x={70} y={972} width={580} height={32} fontFamily="Inter" fontSize={24} color="#103F3D" align="center">See if you qualify</text>
    <text x={62} y={1017} width={596} height={48} fontFamily="Inter" fontSize={36} fontWeight={700} color="#103F3D" align="center">specialistsincare.com</text>
    <text x={70} y={1095} width={580} height={32} fontFamily="Inter" fontSize={19} color="#45635D" align="center">Eligibility and program rules apply.</text>
  </frame>, {at:5.9,dur:1.1,name:"Website over scene"});
  p.compose(<frame width={720} height={1280} layout="none" background="#103F3D">
    <rect x={308} y={363} width={104} height={6} radius={3} fill="#BDE6CF"/>
    <text x={55} y={418} width={610} height={55} fontFamily="Inter" fontSize={28} fontWeight={700} color="#BDE6CF" align="center">SPECIALISTS IN CARE</text>
    <text x={45} y={501} width={630} height={75} fontFamily="Inter" fontSize={60} fontWeight={700} color="#FFF9ED" align="center">Care for Mom.</text>
    <text x={45} y={580} width={630} height={75} fontFamily="Inter" fontSize={60} fontWeight={700} color="#FFF9ED" align="center">Keep family close.</text>
    <rect x={45} y={731} width={630} height={105} radius={22} fill="#FFF9ED"/>
    <text x={60} y={760} width={600} height={51} fontFamily="Inter" fontSize={36} fontWeight={700} color="#103F3D" align="center">specialistsincare.com</text>
    <text x={50} y={873} width={620} height={38} fontFamily="Inter" fontSize={25} color="#FFF9ED" align="center">See if you qualify</text>
    <text x={50} y={1100} width={620} height={36} fontFamily="Inter" fontSize={19} color="#BDE6CF" align="center">Eligibility and program rules apply.</text>
  </frame>,{at:7,dur:1,name:"Closing card"});
  await p.render("/home/user/clean-native.mp4",{bitrate:5000000});
};
