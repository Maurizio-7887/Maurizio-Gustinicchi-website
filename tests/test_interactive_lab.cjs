/* Run: node --test tests/test_interactive_lab.cjs. No Flask, database or network. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {calculateMargin, assess} = require('../static/js/interactive-lab.js');
const sample = {revenue:500000,variable:250000,fixed:150000,discount:5,days:60,targetDays:45};
test('example: discount reduces profit, faster collections release capital not profit', () => {
 const r=calculateMargin(sample); assert.equal(r.operating,100000); assert.equal(r.scenarioOperating,75000);
 assert.equal(r.revenueLoss,25000); assert.equal(r.operatingRate,20);
 assert.ok(Math.abs(r.daysOnlyRelease-20547.94520547945)<1e-8);
 assert.equal(r.scenarioReceivables,475000/365*45);
});
test('unchanged scenario',()=>{const r=calculateMargin({...sample,discount:0,targetDays:60});assert.equal(r.operating,r.scenarioOperating);assert.equal(r.daysOnlyRelease,0);});
test('100 percent discount does not divide by zero',()=>{const r=calculateMargin({...sample,discount:100});assert.equal(r.scenarioRate,null);assert.equal(r.scenarioOperating,-400000);});
test('slower collection absorbs capital without changing operating profit',()=>{const r=calculateMargin({...sample,discount:0,targetDays:90});assert.ok(r.daysOnlyRelease<0);assert.equal(r.scenarioOperating,r.operating);});
test('negative contribution is allowed and reported honestly',()=>{const r=calculateMargin({...sample,variable:600000});assert.ok(r.operating<0);});
test('invalid input rejected',()=>{for(const change of [{revenue:0},{fixed:-1},{discount:101},{days:1.5},{targetDays:731},{revenue:Infinity},{variable:NaN},{discount:'5'}])assert.throws(()=>calculateMargin({...sample,...change}),RangeError);});
test('self assessment counts practices, no arbitrary score',()=>{assert.deepEqual(assess([0,1,2,0,1,2,2,2]),{toExplore:2,partial:2,systematic:4});});
test('all systematic and all unknown handled',()=>{assert.equal(assess(Array(8).fill(2)).systematic,8);assert.equal(assess(Array(8).fill(0)).toExplore,8);});
test('incomplete or invalid self assessment rejected',()=>{assert.throws(()=>assess([0]),RangeError);assert.throws(()=>assess(Array(8).fill(3)),RangeError);});
