import sys, json, os, math, gzip, shutil, argparse, hashlib

from paraview import simple
from paraview.vtk import *

# -----------------------------------------------------------------------------

arrayTypesMapping = '  bBhHiIlLfdL' # last one is idtype

jsMapping = {
    'b': 'Int8Array',
    'B': 'Uint8Array',
    'h': 'Int16Array',
    'H': 'Int16Array',
    'i': 'Int32Array',
    'I': 'Uint32Array',
    'l': 'Int32Array',
    'L': 'Uint32Array',
    'f': 'Float32Array',
    'd': 'Float64Array'
}

writerMapping = {}

# -----------------------------------------------------------------------------

def getRangeInfo(array, component):
  r = array.GetRange(component)
  compRange = {}
  compRange['min'] = r[0]
  compRange['max'] = r[1]
  compRange['component'] = array.GetComponentName(component)
  return compRange

# -----------------------------------------------------------------------------

def getRef(destDirectory, md5):
  ref = {}
  ref['id'] = md5
  ref['encode'] = 'BigEndian' if sys.byteorder == 'big' else 'LittleEndian'
  ref['basepath'] = destDirectory
  return ref

# -----------------------------------------------------------------------------

def dumpStringArray(datasetDir, dataDir, array, root = {}, compress = True):
  if not array:
    return None

  stringArray = []
  arraySize = array.GetNumberOfTuples()
  for i in range(arraySize):
    stringArray.append(array.GetValue(i))

  strData = json.dumps(stringArray)

  pMd5 = hashlib.md5(strData).hexdigest()
  pPath = os.path.join(dataDir, pMd5)
  with open(pPath, 'wb') as f:
    f.write(strData)

  if compress:
    with open(pPath, 'rb') as f_in, gzip.open(os.path.join(dataDir, pMd5 + '.gz'), 'wb') as f_out:
      shutil.copyfileobj(f_in, f_out)
      os.remove(pPath)

  root['ref'] = getRef(os.path.relpath(dataDir, datasetDir), pMd5)
  root['type'] = 'StringArray'
  root['name'] = array.GetName()
  root['dataType'] = 'JSON'
  root['tuple'] = array.GetNumberOfComponents()
  root['size'] = array.GetNumberOfComponents() * array.GetNumberOfTuples()

  return root

# -----------------------------------------------------------------------------

def dumpDataArray(datasetDir, dataDir, array, root = {}, compress = True):
  if not array:
    return None

  if array.GetDataType() == 12:
    # IdType need to be converted to Uint32
    arraySize = array.GetNumberOfTuples() * array.GetNumberOfComponents()
    newArray = vtkTypeUInt32Array()
    newArray.SetNumberOfTuples(arraySize)
    for i in range(arraySize):
      newArray.SetValue(i, -1 if array.GetValue(i) < 0 else array.GetValue(i))
    pBuffer = buffer(newArray)
  else:
    pBuffer = buffer(array)

  pMd5 = hashlib.md5(pBuffer).hexdigest()
  pPath = os.path.join(dataDir, pMd5)
  with open(pPath, 'wb') as f:
    f.write(pBuffer)

  if compress:
    with open(pPath, 'rb') as f_in, gzip.open(os.path.join(dataDir, pMd5 + '.gz'), 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
        os.remove(pPath)

  # print array
  # print array.GetName(), '=>', jsMapping[arrayTypesMapping[array.GetDataType()]]

  root['ref'] = getRef(os.path.relpath(dataDir, datasetDir), pMd5)
  root['type'] = 'DataArray'
  root['name'] = array.GetName()
  root['dataType'] = jsMapping[arrayTypesMapping[array.GetDataType()]]
  root['tuple'] = array.GetNumberOfComponents()
  root['size'] = array.GetNumberOfComponents() * array.GetNumberOfTuples()
  root['ranges'] = []
  if root['tuple'] > 1:
    for i in range(root['tuple']):
      root['ranges'].append(getRangeInfo(array, i))
    root['ranges'].append(getRangeInfo(array, -1))
  else:
    root['ranges'].append(getRangeInfo(array, 0))

  return root

# -----------------------------------------------------------------------------

def dumpAttributes(datasetDir, dataDir, dataset, root = {}, compress = True):
  # PointData
  _pointData = root['PointData'] = {}
  _nbFields = dataset.GetPointData().GetNumberOfArrays()
  for i in range(_nbFields):
    array = dataset.GetPointData().GetArray(i)
    abstractArray = dataset.GetPointData().GetAbstractArray(i)
    if array:
      _array = dumpDataArray(datasetDir, dataDir, array, {}, compress)
      if _array:
        _pointData[_array['name']] = _array
    elif abstractArray:
      _array = dumpStringArray(datasetDir, dataDir, abstractArray, {}, compress)
      if _array:
        _pointData[_array['name']] = _array

  # CellData
  _cellData = root['CellData'] = {}
  _nbFields = dataset.GetCellData().GetNumberOfArrays()
  for i in range(_nbFields):
    array = dataset.GetCellData().GetArray(i)
    abstractArray = dataset.GetCellData().GetAbstractArray(i)
    if array:
      _array = dumpDataArray(datasetDir, dataDir, array, {}, compress)
      if _array:
        _cellData[_array['name']] = _array
    elif abstractArray:
      _array = dumpStringArray(datasetDir, dataDir, abstractArray, {}, compress)
      if _array:
        _cellData[_array['name']] = _array

  # FieldData
  _fieldData = root['FieldData'] = {}
  _nbFields = dataset.GetFieldData().GetNumberOfArrays()
  for i in range(_nbFields):
    array = dataset.GetFieldData().GetArray(i)
    abstractArray = dataset.GetFieldData().GetAbstractArray(i)
    if array:
      _array = dumpDataArray(datasetDir, dataDir, array, {}, compress)
      if _array:
        _fieldData[_array['name']] = _array
    elif abstractArray:
      _array = dumpStringArray(datasetDir, dataDir, abstractArray, {}, compress)
      if _array:
        _fieldData[_array['name']] = _array
  return root

# -----------------------------------------------------------------------------

def dumpPolyData(datasetDir, dataDir, dataset, root = {}, compress = True):
  root['type'] = 'PolyData'
  container = root['PolyData'] = {}

  # Points
  points = dumpDataArray(datasetDir, dataDir, dataset.GetPoints().GetData(), {}, compress)
  points['name'] = '_points'
  container['Points'] = points
  # FIXME range...

  # Cells
  _cells = container['Cells'] = {}

  ## Verts
  if dataset.GetVerts():
    _verts = dumpDataArray(datasetDir, dataDir, dataset.GetVerts().GetData(), {}, compress)
    _verts['name'] = '_verts'
    _cells['Verts'] = _verts

  ## Lines
  if dataset.GetLines():
    _lines = dumpDataArray(datasetDir, dataDir, dataset.GetLines().GetData(), {}, compress)
    _lines['name'] = '_lines'
    _cells['Lines'] = _lines

  ## Polys
  if dataset.GetPolys():
    _polys = dumpDataArray(datasetDir, dataDir, dataset.GetPolys().GetData(), {}, compress)
    _polys['name'] = '_polys'
    _cells['Polys'] = _polys

  ## Strips
  if dataset.GetStrips():
    _strips = dumpDataArray(datasetDir, dataDir, dataset.GetStrips().GetData(), {}, compress)
    _strips['name'] = '_strips'
    _cells['Strips'] = _strips

  # Attributes (PointData, CellData, FieldData)
  dumpAttributes(datasetDir, dataDir, dataset, container, compress)

  return root

# -----------------------------------------------------------------------------
writerMapping['vtkPolyData'] = dumpPolyData
# -----------------------------------------------------------------------------

def dumpUnstructuredGrid(datasetDir, dataDir, dataset, root = {}, compress = True):
  root['type'] = 'UnstructuredGrid'
  container = root['UnstructuredGrid'] = {}

  # Points
  points = dumpDataArray(datasetDir, dataDir, dataset.GetPoints().GetData(), {}, compress)
  points['name'] = '_points'
  container['Points'] = points
  # FIXME range...

  # Cells
  container['Cells'] = dumpDataArray(datasetDir, dataDir, dataset.GetCells().GetData(), {}, compress)

  # CellTypes
  container['CellTypes'] = dumpDataArray(datasetDir, dataDir, dataset.GetCellTypesArray(), {}, compress)

  # Attributes (PointData, CellData, FieldData)
  dumpAttributes(datasetDir, dataDir, dataset, container, compress)

  return root

# -----------------------------------------------------------------------------
writerMapping['vtkUnstructuredGrid'] = dumpUnstructuredGrid
# -----------------------------------------------------------------------------

def dumpImageData(datasetDir, dataDir, dataset, root = {}, compress = True):
  root['type'] = 'ImageData'
  container = root['ImageData'] = {}

  # Origin / Spacing / Dimension
  container['Origin'] = tuple(dataset.GetOrigin())
  container['Spacing'] = tuple(dataset.GetSpacing())
  container['Dimensions'] = tuple(dataset.GetDimensions())

  # Attributes (PointData, CellData, FieldData)
  dumpAttributes(datasetDir, dataDir, dataset, container, compress)

  return root

# -----------------------------------------------------------------------------
writerMapping['vtkImageData'] = dumpImageData
# -----------------------------------------------------------------------------

def dumpRectilinearGrid(datasetDir, dataDir, dataset, root = {}, compress = True):
  root['type'] = 'RectilinearGrid'
  container = root['RectilinearGrid'] = {}

  # Dimensions
  container['Dimensions'] = tuple(dataset.GetDimensions())

  # X, Y, Z
  container['XCoordinates'] = dumpDataArray(datasetDir, dataDir, dataset.GetXCoordinates(), {}, compress)
  container['YCoordinates'] = dumpDataArray(datasetDir, dataDir, dataset.GetYCoordinates(), {}, compress)
  container['ZCoordinates'] = dumpDataArray(datasetDir, dataDir, dataset.GetZCoordinates(), {}, compress)

  # Attributes (PointData, CellData, FieldData)
  dumpAttributes(datasetDir, dataDir, dataset, container, compress)

  return root

# -----------------------------------------------------------------------------
writerMapping['vtkRectilinearGrid'] = dumpRectilinearGrid
# -----------------------------------------------------------------------------

def dumpTable(datasetDir, dataDir, dataset, root = {}, compress = True):
  root['type'] = 'Table'
  container = root['Table'] = {}

  # Columns
  _columns = container['Columns'] = {}
  _nbFields = dataset.GetNumberOfColumns()
  for i in range(_nbFields):
    array = dumpDataArray(datasetDir, dataDir, dataset.GetColumn(i), {}, compress)
    if array:
      _columns[array['name']] = array

  return root

# -----------------------------------------------------------------------------
writerMapping['vtkTable'] = dumpTable
# -----------------------------------------------------------------------------

def dumpMultiBlock(datasetDir, dataDir, dataset, root = {}, compress = True):
  root['type'] = 'MultiBlock'
  container = root['MultiBlock'] = {}

  _blocks = container['Blocks'] = {}
  _nbBlocks = dataset.GetNumberOfBlocks()
  for i in range(_nbBlocks):
    name = dataset.GetMetaData(i).Get(vtkCompositeDataSet.NAME())
    blockDataset = dataset.GetBlock(i)
    if blockDataset:
      writer = writerMapping[blockDataset.GetClassName()]
      if writer:
        _blocks[name] = writer(datasetDir, dataDir, blockDataset, {}, compress)
      else:
        _blocks[name] = blockDataset.GetClassName()

  return root

# -----------------------------------------------------------------------------
writerMapping['vtkMultiBlockDataSet'] = dumpMultiBlock
# -----------------------------------------------------------------------------

def writeDataSet(filePath, dataset, outputDir, newDSName = None, compress = True):
  fileName = newDSName if newDSName else os.path.basename(filePath)
  datasetDir = os.path.join(outputDir, fileName)
  dataDir = os.path.join(datasetDir, 'data')

  if not os.path.exists(dataDir):
    os.makedirs(dataDir)

  root = {}
  root['metadata'] = {}
  root['metadata']['name'] = fileName

  writer = writerMapping[dataset.GetClassName()]
  if writer:
    writer(datasetDir, dataDir, dataset, root, compress)
  else:
    print dataObject.GetClassName(), 'is not supported'

  with open(os.path.join(datasetDir, "index.json"), 'w') as f:
    f.write(json.dumps(root, indent=2))

# -----------------------------------------------------------------------------

def convert(inputFile, outputDir, merge = False, extract = False, newName = None):
  print inputFile, outputDir
  reader = simple.OpenDataFile(inputFile)
  activeSource = reader

  if merge:
    activeSource = simple.MergeBlocks(activeSource)

  if extract:
    activeSource = simple.ExtractSurface(activeSource)

  activeSource.UpdatePipeline()
  dataObject = activeSource.GetClientSideObject().GetOutputDataObject(0)

  writeDataSet(inputFile, dataObject, outputDir, newName)

# -----------------------------------------------------------------------------

def sample(dataDir, outputDir):
  convert(os.path.join(dataDir, 'Data/bot2.wrl'), outputDir, True, True)
  convert(os.path.join(dataDir, 'Data/can.ex2'), outputDir)
  convert(os.path.join(dataDir, 'Data/can.ex2'), outputDir, True, True, 'can_MS.ex2')
  convert(os.path.join(dataDir, 'Data/can.ex2'), outputDir, True, False, 'can_M.ex2')
  convert(os.path.join(dataDir, 'Data/can.ex2'), outputDir, False, True, 'can_S.ex2')
  convert(os.path.join(dataDir, 'Data/disk_out_ref.ex2'), outputDir, True, False, 'disk_out_ref_M.ex2')
  convert(os.path.join(dataDir, 'Data/disk_out_ref.ex2'), outputDir)
  convert(os.path.join(dataDir, 'Data/RectGrid2.vtk'), outputDir)

  # Create image data based on the Wavelet source
  wavelet = simple.Wavelet()
  wavelet.UpdatePipeline()
  imageData = wavelet.GetClientSideObject().GetOutputDataObject(0)
  writeDataSet('Wavelet.vti', imageData, outputDir)

  # Create a table based on the disk_out_ref
  diskout = simple.ExtractSurface(simple.MergeBlocks(simple.OpenDataFile(os.path.join(dataDir, 'Data/disk_out_ref.ex2'))))
  diskout.UpdatePipeline()
  unstructuredGrid = diskout.GetClientSideObject().GetOutputDataObject(0)
  table = vtkTable()
  _nbFields = unstructuredGrid.GetPointData().GetNumberOfArrays()
  for i in range(_nbFields):
    table.AddColumn(unstructuredGrid.GetPointData().GetArray(i))
  writeDataSet('table', table, outputDir)

# =============================================================================
# Main: Parse args and start data conversion
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data conversion")
    parser.add_argument("--input", help="path to the file to convert", dest="input")
    parser.add_argument("--output", help="path to the directory where to write the output", dest="output")
    parser.add_argument("--merge", help="Merge multiblock into single dataset", default=False, action='store_true', dest="merge")
    parser.add_argument("--extract-surface", help="Extract surface mesh", default=False, action='store_true', dest="extract")
    parser.add_argument("--sample-data", help="Generate sample data from ParaView Data", dest="sample")

    args = parser.parse_args()

    if args.sample:
      sample(args.sample, args.output)
    else:
      convert(args.input, args.output, args.merge, args.extract)

