// Native VM APIs consume render pixels and invert the stage scale themselves.
// Layout and browser text retain the original logical 800 x 550 dimensions.
window.moonbaseCoordinates = {
  logicalToRender(x,y) {
    const canvas=document.querySelector('#mount canvas');
    return [x*(canvas?.width||800)/800,y*(canvas?.height||550)/550];
  },
  viewport(camera) {
    const [x,y,w,h]=camera.viewport, canvas=camera.canvas;
    return {left:x*800/canvas.width,top:y*550/canvas.height,width:w*800/canvas.width,height:h*550/canvas.height};
  },
  canvas() { return document.querySelector('#mount canvas'); }
};
