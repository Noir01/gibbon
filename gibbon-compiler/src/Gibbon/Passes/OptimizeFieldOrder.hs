{-# OPTIONS_GHC -Wno-unrecognised-pragmas #-}
{-# HLINT ignore "Use lambda-case" #-}
{-# OPTIONS_GHC -Wno-incomplete-uni-patterns #-}
module Gibbon.Passes.OptimizeFieldOrder
  ( shuffleDataCon,
  )
where

-- Gibbon imports

import Control.Exception (evaluate)
import Data.List as L
-- Haskell imports
import Data.Map as M
import Data.Maybe as Maybe
import Data.Time.Clock
  ( diffUTCTime,
    getCurrentTime,
  )
import Gibbon.Common
import Gibbon.Language
import Gibbon.Language.Syntax
import Gibbon.L1.Syntax
import Gibbon.Passes.AccessPatternsAnalysis
  ( DataConAccessMap,
    FieldMap,
    generateAccessGraphs,
  )
import Gibbon.Passes.CallGraph
  ( ProducersMap (..),
    generateProducerGraph,
  )
import Gibbon.Passes.ControlFlowGraph (getFunctionCFG)
import Gibbon.Passes.DefinitionUseChains
  ( DefUseChainsFunctionMap (..),
    generateDefUseChainsFunction,
    progToVEnv,
  )
import Gibbon.Passes.SolveLayoutConstrs (solveConstrs)
import Gibbon.Pretty
import System.CPUTime
import System.IO.Unsafe as U
import System.TimeIt
import Text.PrettyPrint.GenericPretty
import Prelude as P

-- | Data structure to store output from ILP solver.
-- | Maps DataCon to bijection of new indices -> fields of datacon
type FieldOrder = M.Map DataCon [Integer]

-- TODO: Make FieldOrder an argument passed to shuffleDataCon function.
shuffleDataCon ::
  Prog1 ->
  PassM Prog1
shuffleDataCon prg@Prog{ddefs, fundefs, mainExp} =
  do
    let list_pair_func_dcon =
          concatMap ( \fn@(FunDef {funName, funMeta = FunMeta {funOptLayout = layout}}) ->
                  case layout of
                    Single dcon -> [(fromVar funName, dcon)]
                    -- only handles optimizing a single dcon for a function right now.
                    -- its okay for the current examples
                    -- but should be extended
                    _ -> []
              ) (M.elems fundefs)
    -- If a total ordering is defined for a function (by the user), then we should just use that instead.
    -- The total ordering defined by the user should just override
    -- get the function for which the total ordering is defined and get the corresponding total ordering.
    -- Tuple (funcName, map) map : map from data constructor to the user defined ordering.
    let userConstraints =
          concatMap ( \fn@( FunDef
                        { funName,
                          funMeta = FunMeta {userConstraintsDataCon = totalOrdering}
                        }
                      ) ->
                    case totalOrdering of
                      Nothing -> []
                      Just m -> [(fromVar funName, m)]
              ) (M.elems fundefs)
    -- pure prg
    case userConstraints of
      [] ->
        case list_pair_func_dcon of
          [] -> pure prg
          --TODO: handle for more than one function
          (funcName, dcon) : xs -> do
            let [fundef] =
                  P.concatMap
                    ( \fn@(FunDef {funName}) ->
                        ([fn | fromVar funName == funcName])
                    )
                    (M.elems fundefs)
            let (ddefs', fundef', fieldorder) =
                  optimizeFunctionWRTDataCon ddefs fundef dcon
            let fundefs' = M.delete (toVar funcName) fundefs
            let fundefs'' = M.insert (toVar funcName) fundef' fundefs'
            let venv = progToVEnv prg
            let pmap = generateProducerGraph prg
            let p = prg {ddefs = ddefs', fundefs = fundefs'', mainExp = mainExp}
            let prg' =
                  genNewProducersAndRewriteProgram
                    (toVar funcName)
                    (dcon ++ "tmp")
                    fieldorder
                    venv
                    pmap
                    p
            return prg'
      _ -> error "OptimizeFieldOrder: handle use constraints"


optimizeFunctionWRTDataCon ::
  DDefs1 ->
  FunDef1 ->
  DataCon ->
  (DDefs1, FunDef1, FieldOrder)
optimizeFunctionWRTDataCon
  ddefs
  fundef@FunDef
    { funName,
      funBody,
      funTy,
      funArgs
    }
  datacon =
    let cfg = getFunctionCFG fundef
        fieldMap = generateAccessGraphs cfg M.empty fundef [datacon]
        field_len = P.length $ snd . snd $ lkp' ddefs datacon
        fieldorder =
          optimizeDataConOrderFunc
            fieldMap
            M.empty
            fundef
            [(datacon, field_len)]
            M.empty
        -- make a function to generate a new data con as a value instead of changing the order of fields in the original one.
        [(dcon, order)] = M.toList fieldorder
        (newDDefs, newDcon) = optimizeDataCon (dcon, order) ddefs
        fundef' = shuffleDataConFunBody fieldorder fundef newDcon
     in (newDDefs, fundef', fieldorder)

changeCallNameInRecFunction ::
  Var -> FunDef1 -> FunDef1
changeCallNameInRecFunction
  newFunName
  f@FunDef
    { funName,
      funArgs,
      funTy,
      funBody,
      funMeta
    } =
    case funMeta of
      FunMeta {funRec} ->
        case funRec of
          Rec ->
            f
              { funName = newFunName,
                funArgs = funArgs,
                funTy = funTy,
                funBody = fixExp funBody,
                funMeta
              }
          _ ->
            f
              { funName = newFunName,
                funArgs = funArgs,
                funTy = funTy,
                funBody = funBody,
                funMeta
              }
    where
      fixExp funBody =
        case funBody of
          DataConE loc dcon args -> DataConE loc dcon (P.map fixExp args)
          VarE {} -> funBody
          LitE {} -> funBody
          CharE {} -> funBody
          FloatE {} -> funBody
          LitSymE {} -> funBody
          AppE f locs args ->
            if f == funName
              then AppE newFunName locs (P.map fixExp args)
              else AppE f locs (P.map fixExp args)
          PrimAppE f args -> PrimAppE f (P.map fixExp args)
          LetE (v, loc, ty, rhs) bod ->
            let rhs' = fixExp rhs
                bod' = fixExp bod
             in LetE (v, loc, ty, rhs') bod'
          CaseE scrt mp ->
            let mp' = P.map (\(a, b, c) -> (a, b, fixExp c)) mp
             in CaseE scrt mp'
          IfE a b c -> IfE (fixExp a) (fixExp b) (fixExp c)
          MkProdE xs -> MkProdE (P.map fixExp xs)
          ProjE i e -> error "getExpTyEnv: TODO ProjE"
          TimeIt e ty b -> error "getExpTyEnv: TODO TimeIt"
          WithArenaE v e -> error "getExpTyEnv: TODO WithArenaE"
          SpawnE f locs args -> error "getExpTyEnv: TODO SpawnE"
          SyncE -> error "getExpTyEnv: TODO SyncE"
          Ext _ -> error "getExpTyEnv: TODO Ext"
          MapE {} -> error "getExpTyEnv: TODO MapE"
          FoldE {} -> error "getExpTyEnv: TODO FoldE"

genNewProducersAndRewriteProgram ::
  Var ->
  DataCon ->
  FieldOrder ->
  Env2 Ty1 ->
  ProducersMap Exp1 ->
  Prog Exp1 ->
  Prog Exp1
genNewProducersAndRewriteProgram
  funName
  newDataConName
  newdataConOrder
  venv
  pmap
  prg@Prog
    { ddefs,
      fundefs,
      mainExp
    } =
    case mainExp of
      Nothing ->
        error "genNewProducersAndRewriteProgram : Program has no main expression."
      Just (mexp, ty) ->
        let variablesAndProducers = getVariableAndProducer funName pmap venv ddefs newDataConName mexp
         in case variablesAndProducers of
              [] -> error "no variable and producers found to modify"
              [(var, producer)] ->
                let newProducerName = toVar (fromVar producer ++ "_new")
                    oldProducerBody = M.lookup producer fundefs
                 in case oldProducerBody of
                      Just body ->
                        let newProducerBody@FunDef
                              { funName,
                                funBody,
                                funTy,
                                funArgs
                              } =
                                shuffleDataConFunBody
                                  newdataConOrder
                                  body
                                  newDataConName
                            newProducerBody' =
                              changeCallNameInRecFunction
                                newProducerName
                                newProducerBody
                            fundefs' =
                              M.insert newProducerName newProducerBody' fundefs
                            newMainExp =
                              callNewProducerForVarInMain
                                var
                                False
                                producer
                                newProducerName
                                mexp
                         in prg
                              { ddefs = ddefs,
                                fundefs = fundefs',
                                mainExp = Just (newMainExp, ty)
                              }
                      _ -> error ""
              x : xs -> error "more than one variable and producer not handled yet."

-- Function to find the the variable/s that have the type that's being optimized for the given function f
-- Also return the producer of those variable/s
-- Arguments
-- Var -> Name of the function being optimized
-- pmap -> variable to producer map
-- (PreExp e l d) -> expression to search over
-- Return
-- [(Var, Producer)]
getVariableAndProducer ::
  Var ->
  ProducersMap Exp1 ->
  Env2 Ty1 ->
  DDefs1 ->
  DataCon ->
  Exp1 ->
  [(Var, Var)]
getVariableAndProducer funName pMap venv@Env2{vEnv, fEnv} ddefs dconName exp =
  case exp of
    DataConE loc dcon args ->
      P.concatMap (getVariableAndProducer funName pMap venv ddefs dconName) args
    VarE {} -> []
    LitE {} -> []
    CharE {} -> []
    FloatE {} -> []
    LitSymE {} -> []
    AppE f locs args ->
      P.concatMap (getVariableAndProducer funName pMap venv ddefs dconName) args
    PrimAppE f args ->
      P.concatMap (getVariableAndProducer funName pMap venv ddefs dconName) args
    LetE (v, loc, ty, rhs) bod ->
      let varOf =
            case rhs of
              AppE f locs args ->
                if f == funName
                  then
                    let potentialVarsOfTy =
                          P.map
                            ( \exp ->
                                case exp of
                                  VarE v ->
                                    case lookupVEnv' v venv of
                                      Just e -> let tyCon = getTyOfDataCon ddefs dconName
                                                    urtyTyCon = PackedTy tyCon ()
                                                  in if e == urtyTyCon then Just v
                                                     else Nothing
                                      Nothing -> Nothing
                                  _ -> Nothing
                            )
                            args
                        justVariables = Maybe.catMaybes potentialVarsOfTy
                     in if P.null justVariables
                          then error "getVariableAndProducer: no variables of Ty to optimize found!"
                          else
                            if P.length justVariables > 1
                              then
                                dbgTraceIt
                                  (sdoc justVariables)
                                  Just
                                  (justVariables !! 1) -- error "getVariableAndProducer: Not implemented!"
                              else Just (P.head justVariables)
                  else dbgTraceIt (sdoc f) Nothing
              _ -> Nothing
          producers =
            getVariableAndProducer funName pMap venv ddefs dconName rhs
              ++ getVariableAndProducer funName pMap venv ddefs dconName bod
       in case varOf of
            Just var ->
              let varType = lookupVEnv' var venv
               in case varType of
                    Just ty ->
                      let producerExp = M.lookup (var, ty) pMap 
                       in case producerExp of
                            Just (AppE f locs args) -> (var, f) : producers
                            _ ->
                              error
                                "getVariableAndProducer: producer other than a function call not expected."
                    Nothing -> dbgTraceIt (sdoc (M.elems vEnv)) []
            Nothing -> producers
    -- a == DataCon
    -- b == [(Var, loc)]
    -- c == Case Body
    CaseE scrt mp ->
      P.concatMap (\(a, b, c) -> getVariableAndProducer funName pMap venv ddefs dconName c) mp
    IfE a b c ->
      let producersA = getVariableAndProducer funName pMap venv ddefs dconName a
          producersB = getVariableAndProducer funName pMap venv ddefs dconName b
          producersC = getVariableAndProducer funName pMap venv ddefs dconName c
       in producersA ++ producersB ++ producersC
    MkProdE xs -> P.concatMap (getVariableAndProducer funName pMap venv ddefs dconName) xs
    ProjE i e -> error "getExpTyEnv: TODO ProjE"
    TimeIt e ty b -> error "getExpTyEnv: TODO TimeIt"
    WithArenaE v e -> error "getExpTyEnv: TODO WithArenaE"
    SpawnE f locs args -> error "getExpTyEnv: TODO SpawnE"
    SyncE -> error "getExpTyEnv: TODO SyncE"
    Ext _ -> error "getExpTyEnv: TODO Ext"
    MapE {} -> error "getExpTyEnv: TODO MapE"
    FoldE {} -> error "getExpTyEnv: TODO FoldE"

-- For a variable that's produced change the old producer to the new producer.
-- Args
-- Var  -> Variable whose producer needs to be changed
-- Bool -> a switch for modifying the call or not.
-- Var  -> Name of the old producer
-- Var  -> Name of the new producer
-- (PreExp e l d) -> Main Expression
-- Return value
-- (PreExp e l d) -> New Main Expression
callNewProducerForVarInMain ::
  Var -> Bool -> Var -> Var -> Exp1 -> Exp1
callNewProducerForVarInMain var boolModify oldProducer newProducer mainExp =
  case mainExp of
    DataConE loc dcon args ->
      let args' =
            P.map
              ( callNewProducerForVarInMain
                  var
                  boolModify
                  oldProducer
                  newProducer
              )
              args
       in DataConE loc dcon args'
    VarE {} -> mainExp
    LitE {} -> mainExp
    CharE {} -> mainExp
    FloatE {} -> mainExp
    LitSymE {} -> mainExp
    AppE f locs args ->
      let args' =
            P.map
              ( callNewProducerForVarInMain
                  var
                  boolModify
                  oldProducer
                  newProducer
              )
              args
       in if f == oldProducer && boolModify
            then AppE newProducer locs args'
            else AppE f locs args'
    PrimAppE f args ->
      let args' =
            P.map
              ( callNewProducerForVarInMain
                  var
                  boolModify
                  oldProducer
                  newProducer
              )
              args
       in PrimAppE f args'
    LetE (v, loc, ty, rhs) bod ->
      let rhs' =
            if v == var
              then
                callNewProducerForVarInMain
                  var
                  True
                  oldProducer
                  newProducer
                  rhs
              else
                callNewProducerForVarInMain
                  var
                  False
                  oldProducer
                  newProducer
                  rhs
          bod' =
            callNewProducerForVarInMain
              var
              boolModify
              oldProducer
              newProducer
              bod
       in LetE (v, loc, ty, rhs') bod'
    -- a == DataCon
    -- b == [(Var, loc)]
    -- c == Case Body
    CaseE scrt mp ->
      let mp' =
            P.map
              ( \(a, b, c) ->
                  let c' =
                        callNewProducerForVarInMain
                          var
                          boolModify
                          oldProducer
                          newProducer
                          c
                   in (a, b, c')
              )
              mp
       in CaseE scrt mp'
    IfE a b c ->
      let a' =
            callNewProducerForVarInMain var boolModify oldProducer newProducer a
          b' =
            callNewProducerForVarInMain var boolModify oldProducer newProducer b
          c' =
            callNewProducerForVarInMain var boolModify oldProducer newProducer c
       in IfE a' b' c'
    MkProdE xs ->
      let xs' =
            P.map
              ( callNewProducerForVarInMain
                  var
                  boolModify
                  oldProducer
                  newProducer
              )
              xs
       in MkProdE xs'
    ProjE i e -> error "getExpTyEnv: TODO ProjE"
    TimeIt e ty b -> error "getExpTyEnv: TODO TimeIt"
    WithArenaE v e -> error "getExpTyEnv: TODO WithArenaE"
    SpawnE f locs args -> error "getExpTyEnv: TODO SpawnE"
    SyncE -> error "getExpTyEnv: TODO SyncE"
    Ext _ -> error "getExpTyEnv: TODO Ext"
    MapE {} -> error "getExpTyEnv: TODO MapE"
    FoldE {} -> error "getExpTyEnv: TODO FoldE"

genEdgesFromTotalOrdering ::
  [(String, DataConMap)] -> [FunDef1] -> FieldMap -> FieldMap
genEdgesFromTotalOrdering lstTotalOrdering fundefs mapIn =
  case lstTotalOrdering of
    [] -> mapIn
    x : xs ->
      let (funcName, map) = x
          [fundef@(FunDef {funName})] =
            concatMap ( \fn@(FunDef {funName}) ->
                    ([fn | fromVar funName == funcName])
                ) fundefs
          dconOrderings = M.toList map
          dconOrderings' =
            P.map
              ( \(dcon, strongOrderings) ->
                  let edges =
                        P.map
                          ( \(Strong a b) -> ((a, b), P.toInteger (100 :: Integer))
                          )
                          strongOrderings
                   in (dcon, edges)
              )
              dconOrderings
          orderMap = M.fromList dconOrderings'
          newMap = M.insert funName orderMap mapIn
          newMap' = genEdgesFromTotalOrdering xs fundefs newMap
       in newMap'

existsTuple :: [(String, a)] -> String -> Bool
existsTuple lst name =
  case lst of
    [] -> False
    (x, y) : xs ->
      x == name || existsTuple xs name

-- This just goes through the function we are locally optimizing
-- Since this problem is to locally optimize for a particular function right now we are not concerned with finding the best
-- optimal layout for the complete program.
locallyOptimizeFieldOrdering ::
  FieldMap ->
  [DataCon] ->
  [FunDef1] ->
  String ->
  Int ->
  FieldOrder ->
  Int ->
  FieldOrder
locallyOptimizeFieldOrdering fieldMap dcons fundefs funcName field_len orderIn mode =
  case fundefs of
    [] -> orderIn
    x : xs ->
      let map' =
            generateLocallyOptimalOrderings
              fieldMap
              dcons
              x
              funcName
              field_len
              orderIn
              mode
          map'' =
            locallyOptimizeFieldOrdering
              fieldMap
              dcons
              xs
              funcName
              field_len
              map'
              mode
       in map''


genUserConstrs :: [UserOrdering] -> [Constr]
genUserConstrs userOrdering =
  case userOrdering of
    (Strong a b) : xs -> Absolute (a, b) : genUserConstrs xs
    (Immediate a b) : xs -> Imm (a, b) : genUserConstrs xs
    [] -> []

-- Takes in Field access map
-- Takes in user constraints for data con for that function
-- takes in the function def for the function
-- Takes in [(DataCon, Int)], ie, data con name, and number of fields for data constructors that need to be optimized
-- Returns optimal order of fields of a data constructor.

-- Timing for filtering the blogs based on a keyword
timeSolver ::
  (IO [(Int, Int)] -> [(Int, Int)]) ->
  IO [(Int, Int)] ->
  IO ([(Int, Int)], Double)
timeSolver f f' = do
  t1 <- getCurrentTime
  a <- evaluate (f f')
  t2 <- getCurrentTime
  let delt = fromRational (toRational (diffUTCTime t2 t1))
  putStrLn ("iter time: " ++ show delt)
  return (a, delt)

optimizeDataConOrderFunc ::
  FieldMap ->
  DataConMap ->
  FunDef1 ->
  [(DataCon, Int)] ->
  FieldOrder ->
  FieldOrder
optimizeDataConOrderFunc
  dconAccessMap
  dconUserConstr
  fundef@FunDef
    { funName,
      funBody,
      funTy,
      funArgs
    }
  datacons
  orderIn =
    let lstDconEdges = M.findWithDefault M.empty funName dconAccessMap
     in case datacons of
          [] -> orderIn
          [(x, field_len)] ->
            let softEdges = M.findWithDefault [] x lstDconEdges
                softConstrs = P.map Soft softEdges
                userOrdering = M.findWithDefault [] x dconUserConstr
                userConstrs = genUserConstrs userOrdering
                allConstrs = softConstrs ++ userConstrs
             in -- field_len    = P.length $ snd . snd $ lkp ddefs x
                case allConstrs of
                  [] -> orderIn
                  _ ->
                    let (layout, t) =
                          U.unsafePerformIO $
                            timeSolver U.unsafePerformIO (solveConstrs allConstrs)
                        -- In case we don't get orderings for some of the fields in the data con
                        -- to be safe we should complete the layout orderings of the missing fields.
                        fix_missing =
                          if P.length layout < field_len
                            then
                              let indices = [0 .. (field_len - 1)]
                                  minuslist = makeneg field_len
                                  partial = fillList minuslist layout
                                  avail = P.map fst layout
                                  navail = deleteMany avail indices
                                  new = fillminus1 partial navail
                               in new
                            else
                              let layout' = L.sort layout
                               in P.map snd layout'
                        fieldorder = M.insert x (integerList fix_missing) orderIn
                     in fieldorder
          _ ->
            error
              "OptimizeFieldOrder: optimizeDataConOrderFunc more that one data constructor per function not implemented yet."

-- for the function for which we are locally optimizing for, find the optimal layout of the data constructors that we care about.
-- "Locally optimizing for the function"
generateLocallyOptimalOrderings ::
  FieldMap ->
  [DataCon] ->
  FunDef1 ->
  String ->
  Int ->
  FieldOrder ->
  Int ->
  FieldOrder
generateLocallyOptimalOrderings
  fieldMap
  datacons
  fundef@FunDef
    { funName,
      funBody,
      funTy,
      funArgs
    }
  funcName
  field_len
  orderIn
  mode =
    if fromVar funName == funcName
      then
        let lstDconEdges = M.findWithDefault M.empty funName fieldMap
         in case datacons of
              [] -> orderIn
              x : xs ->
                let dconEdges = M.findWithDefault [] x lstDconEdges
                    dconEdges' = P.map Soft dconEdges
                 in case dconEdges' of
                      [] -> orderIn
                      _ ->
                        let layout =
                              U.unsafePerformIO (solveConstrs dconEdges')
                            -- In case we don't get orderings for some of the fields in the data con
                            -- to be safe we should complete the layout orderings of the missing fields.
                            fix_missing =
                              if P.length layout < field_len
                                then
                                  let indices = [0 .. (field_len - 1)]
                                      minuslist = makeneg field_len
                                      partial = fillList minuslist layout
                                      avail = P.map fst layout
                                      navail = deleteMany avail indices
                                      new = fillminus1 partial navail
                                   in new
                                else
                                  let layout' = L.sort layout
                                   in P.map snd layout'
                            fieldorder =
                              M.insert x (integerList fix_missing) orderIn
                            fieldorder' =
                              generateLocallyOptimalOrderings
                                fieldMap
                                xs
                                fundef
                                funcName
                                field_len
                                fieldorder
                                mode
                         in dbgTraceIt
                              (sdoc dconEdges)
                              dbgTraceIt
                              "\n"
                              dbgTraceIt
                              (sdoc fieldorder')
                              dbgTraceIt
                              "\n"
                              fieldorder'
      else orderIn

makeneg :: Int -> [Int]
makeneg len =
  if len <= 0
    then []
    else makeneg (len - 1) ++ [-1]

integerList :: [Int] -> [Integer]
integerList lst =
  case lst of
    [] -> []
    x : xs -> P.toInteger x : integerList xs

fillList :: [Int] -> [(Int, Int)] -> [Int]
fillList old vals =
  case vals of
    [] -> old
    x : xs ->
      let (a, b) = x
          edited = L.take b old ++ [a] ++ L.drop (b + 1) old
       in fillList edited xs

-- https://www.reddit.com/r/haskell/comments/u841av/trying_to_remove_all_the_elements_that_occur_in/
deleteOne :: (Eq a) => a -> [a] -> [a]
deleteOne _ [] = [] -- Nothing to delete
deleteOne x (y : ys)
  | x == y = ys -- Drop exactly one matching item
deleteOne x (y : ys) = y : deleteOne x ys -- Drop one, but not this one (doesn't match).

deleteMany :: (Eq a) => [a] -> [a] -> [a]
deleteMany [] = id -- Nothing to delete
deleteMany (x : xs) = deleteMany xs . deleteOne x -- Delete one, then the rest.

fillminus1 :: [Int] -> [Int] -> [Int]
fillminus1 lst indices =
  case lst of
    [] -> []
    x : xs ->
      case indices of
        [] -> lst
        y : ys ->
          if x == -1
            then y : fillminus1 xs ys
            else x : fillminus1 xs indices

shuffleDataConFunBody ::
  FieldOrder -> FunDef1 -> DataCon -> FunDef1
shuffleDataConFunBody fieldorder f@FunDef {funBody} newDataCon =
  let funBody' = shuffleDataConExp fieldorder newDataCon funBody
   in f {funBody = funBody'}

shuffleDataConExp :: FieldOrder -> DataCon -> Exp1 -> Exp1
shuffleDataConExp fieldorder newDataCon ex =
  case ex of
    DataConE loc dcon args ->
      let args' = shuffleDataConArgs fieldorder dcon args
          newCon =
            if M.member dcon fieldorder
              then newDataCon
              else dcon
       in DataConE loc newCon args'
    VarE {} -> ex
    LitE {} -> ex
    CharE {} -> ex
    FloatE {} -> ex
    LitSymE {} -> ex
    AppE f locs args ->
      AppE f locs (P.map (shuffleDataConExp fieldorder newDataCon) args)
    PrimAppE f args ->
      PrimAppE f (P.map (shuffleDataConExp fieldorder newDataCon) args)
    LetE (v, loc, ty, rhs) bod ->
      let rhs' = shuffleDataConExp fieldorder newDataCon rhs
          bod' = shuffleDataConExp fieldorder newDataCon bod
       in LetE (v, loc, ty, rhs') bod'
    IfE a b c ->
      let a' = shuffleDataConExp fieldorder newDataCon a
          b' = shuffleDataConExp fieldorder newDataCon b
          c' = shuffleDataConExp fieldorder newDataCon c
       in IfE a' b' c'
    MkProdE xs -> MkProdE (P.map (shuffleDataConExp fieldorder newDataCon) xs)
    ProjE i e -> ProjE i (shuffleDataConExp fieldorder newDataCon e)
    CaseE scrt mp ->
      let mp' =
            P.map
              ( \(a, b, c) ->
                  let b' = shuffleDataConCase fieldorder a b
                      c' = shuffleDataConExp fieldorder newDataCon c
                      a' =
                        if M.member a fieldorder
                          then newDataCon
                          else a
                   in (a', b', c')
              )
              mp
       in CaseE scrt mp'
    TimeIt e ty b ->
      let e' = shuffleDataConExp fieldorder newDataCon e
       in TimeIt e' ty b
    WithArenaE v e ->
      let e' = shuffleDataConExp fieldorder newDataCon e
       in WithArenaE v e'
    SpawnE f locs args ->
      SpawnE f locs (P.map (shuffleDataConExp fieldorder newDataCon) args)
    SyncE -> SyncE
    Ext _ -> ex
    MapE {} -> error "shuffleFieldOrdering: TODO MapE"
    FoldE {} -> error "shuffleFieldOrdering: TODO FoldE"

shuffleDataConArgs ::
  FieldOrder -> DataCon -> [Exp1] -> [Exp1]
shuffleDataConArgs fieldorder dcon exps =
  if M.member dcon fieldorder
    then permute (findWithDefault [] dcon fieldorder) exps
    else exps

shuffleDataConCase :: FieldOrder -> DataCon -> [(Var, loc)] -> [(Var, loc)]
shuffleDataConCase fieldorder dcon vs =
  if M.member dcon fieldorder
    then permute (findWithDefault [] dcon fieldorder) vs
    else vs


optimizeDataCon ::
  (DataCon, [Integer]) ->
  DDefs1 ->
  (DDefs1, DataCon)
optimizeDataCon (dcon, newindices) ddefs =
  let (tycon, (_, fields)) = lkp' ddefs dcon
      newFields = permute newindices fields
      newDcon = dcon ++ "tmp" -- TODO: Change this to use gensym
      DDef {tyName, tyArgs, dataCons} = lookupDDef' ddefs (fromVar tycon)
      newDDef =
        DDef
          { tyName = tyName,
            tyArgs = tyArgs,
            dataCons = dataCons ++ [(newDcon, newFields)]
          }
      ddefs' = M.delete tycon ddefs
      ddefs'' = insertDD newDDef ddefs'
   in (ddefs'', newDcon)

-- | Lookup a Datacon.  Return (TyCon, (DataCon, [flds]))
lkp' ::
  DDefs1 ->
  DataCon ->
  (Var, (DataCon, [(IsBoxed, UrTy())]))
lkp' dds con =
  -- Here we try to lookup in ALL datatypes, assuming unique datacons:
  case [ (tycon, variant)
         | (tycon, DDef {dataCons}) <- M.toList dds,
           variant <- L.filter ((== con) . fst) dataCons
       ] of
    [] ->
      error "OptimizeFieldOrder -> lookupDataCon: could not find constructor!"
    [hit] -> hit
    _ ->
      error "OptimizeFieldOrder -> lookupDataCon: found multiple occurences of constructor!"

-- | Lookup a ddef in its entirety
lookupDDef' ::
  DDefs1 -> TyCon -> DDef1
lookupDDef' mp tycon =
  case M.lookup (toVar tycon) mp of
    Just x -> x
    Nothing -> error "OptimizeFieldOrder: lookupDDef' failed!"

permute :: [Integer] -> [a] -> [a]
permute indices list =
  case indices of
    [] -> []
    x : xs -> (list !! P.fromInteger x) : permute xs list
