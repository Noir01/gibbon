{-# LANGUAGE NamedFieldPuns #-}
{-# LANGUAGE PatternSynonyms #-}
{-# LANGUAGE StandaloneDeriving #-}
{-# LANGUAGE OverloadedStrings #-}
{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE TupleSections #-}
{-# OPTIONS_GHC -fno-warn-orphans #-}
{-# OPTIONS_GHC -fno-warn-name-shadowing #-}
{-# OPTIONS_GHC -fdefer-typed-holes #-}
{-# OPTIONS_GHC -fno-warn-missing-pattern-synonym-signatures #-}

-- |  Parse an SExp representaton of our tree-walk language.

module Packed.FirstOrder.L2.Parser
       (parseFile, parseSExp) where

import Data.List as L
import Data.Loc
import Data.Map as M
import Data.Set as S
import Data.Text as T hiding (head)
import Data.Text.IO (readFile)
import System.FilePath
import Text.Parsec
-- import GHC.Generics (Generic)
import Text.PrettyPrint.GenericPretty
import Prelude hiding (readFile, exp)

-- There are several options for s-expression parsing, including these
-- packages on Hackage:
--  * sexp
--  * sexpr
--  * sexp-grammar
--  * atto-lisp
--  * lispparser
-- Using 's-cargo' for the first attempt:
import Data.SCargot.Language.HaskLike
import Data.SCargot.Parse
import Data.SCargot.Print
import Data.SCargot.Repr -- (SExpr, RichSExpr, toRich)
import qualified Data.SCargot.Common as SC

import Packed.FirstOrder.L2.Syntax as L2
import qualified Packed.FirstOrder.L1.Syntax as L1
import Packed.FirstOrder.Common hiding (insertFD, fromListFD)

--------------------------------------------------------------------------------

-- | Baseline chatter level for this module:
lvl :: Int
lvl = 5      

deriving instance Generic (SExpr a)
deriving instance Generic (RichSExpr a)
deriving instance Generic HaskLikeAtom
instance (Generic a, Out a) => Out (SExpr a)
instance (Generic a, Out a) => Out (RichSExpr a)
instance Out HaskLikeAtom
instance Out Text where
  doc t = doc (T.unpack t)
  docPrec n t = docPrec n (T.unpack t)

type Sexp = RichSExpr (SC.Located HaskLikeAtom)

prnt :: Sexp -> String
prnt = T.unpack . encodeOne locatedHaskLikePrinter . fromRich

textToVar :: Text -> Var
textToVar = toVar . T.unpack

textToDataCon :: Text -> DataCon
textToDataCon = T.unpack

-- | Convert Location (s-cargot) to Loc (Data.Loc)
-- s-cargot uses SrcPos exported by Parsec whereas Data.Loc has it's own notion of Pos
toLoc :: SC.Location -> Loc
toLoc (SC.Span start end) = Loc (toPos start) (toPos end)

toPos :: SourcePos -> Pos
toPos sp = Pos name line col 0
  where name = sourceName sp
        line = sourceLine sp
        col  = sourceColumn sp

loc :: SC.Location -> a -> L a
loc l = L (toLoc l)

typ :: Sexp -> Ty2
typ s = case s of
         (A _ "Int")  -> IntTy
         (A _ "Sym")  -> SymTy
         (A _ "Bool") -> BoolTy
         (RSList [A _ dtype, A _ l]) -> L1.PackedTy (textToDataCon dtype) (textToVar l)
         (RSList (A _ "Vector"  : rst)) -> ProdTy $ L.map typ rst
         (RSList [A _ "SymDict", t]) -> SymDictTy $ typ t
         (RSList [A _ "Listof", t])  -> ListTy $ typ t
         _ -> error$ "SExpression encodes invalid type:\n "++prnt s

getSym :: Sexp -> Var
getSym (A _ id) = textToVar id
getSym s = error $ "expected identifier sexpr, got: "++prnt s

pattern A loc s = RSAtom (SC.At loc (HSIdent s))
pattern G loc s = RSAtom (SC.At loc s)
pattern Ls0 a             = RSList a
pattern Ls1 a             = RSList [a]
pattern Ls2 loc a b       = RSList [A loc a, b]
pattern Ls3 loc a b c     = RSList [A loc a, b, c]
pattern Ls4 loc a b c d   = RSList [A loc a, b, c, d]
-- pattern L5 a b c d e = RSList [A a, b, c, d, e]

trueE :: Exp2
trueE = PrimAppE L1.MkTrue []

falseE :: Exp2
falseE = PrimAppE L1.MkFalse []

keywords :: S.Set Text
keywords = S.fromList $ L.map pack $
           [ "quote", "if", "or", "and", "time", "let"
           , "case", "vector-ref", "for/fold", "for/list"
           , "insert", "empty-dict", "lookup", "error", "ann"
           ]

isKeyword :: Text -> Bool
isKeyword s = s `S.member` keywords

isPrim :: Text -> Bool
isPrim p = S.member p (M.keysSet primMap)

primMap :: Map Text (L1.Prim Ty2)
primMap = M.fromList
  [ ("+", L1.AddP)
  , ("-", L1.SubP)
  , ("*", L1.MulP)
  , ("/", L1.DivP)
  , ("mod", L1.ModP)
  , ("eq?", L1.EqSymP)
  , ("=", L1.EqIntP)
  , ("<", L1.LtP)
  , (">", L1.GtP)
  , ("size-param", L1.SizeParam)
  , ("sym-append", L1.SymAppend)
  ]

prim :: Text -> L1.Prim Ty2
prim t = case M.lookup t primMap of
           Just x -> x
           Nothing -> error$ "Internal error, this is not a primitive: "++show t

handleRequire :: FilePath -> [RichSExpr (SC.Located HaskLikeAtom)] ->
                 IO [RichSExpr (SC.Located HaskLikeAtom)]
handleRequire _ [] = return []
handleRequire baseFile (l:ls) =
  case l of
    (RSList [RSAtom (SC.At _ "require"), arg]) -> do
    -- (Ls2 "require" arg) -> do
       ls' <- handleRequire baseFile ls
       let file = case arg of
                    RSAtom (SC.At _ (HSString str)) -> (takeDirectory baseFile) </> (unpack str)
                    _ -> error $ "bad require line: " ++ (show arg)
       dbgPrintLn lvl $ "Including required file: "++show file
       txt <- fmap bracketHacks $ readFile file
       dbgPrintLn lvl $ "Parsing required text: "++show txt
       let res :: Either String [RichSExpr (SC.Located HaskLikeAtom)]
           res = fmap (fmap toRich) $
                 decode treelangParser txt
       case res of
         Left err -> error err
         -- Right ls -> return $ ls ++ ls'
         Right l' -> return $ l' ++ ls'
    _ -> do
      ls' <- handleRequire baseFile ls
      return $ l:ls'

parseFile :: FilePath -> IO (Prog, Int)
parseFile file = do
  txt    <- fmap bracketHacks $
            -- fmap stripHashLang $
            readFile file
  dbgPrintLn lvl $ "Parsing text: "++show txt
  let res :: Either String [RichSExpr (SC.Located HaskLikeAtom)]
      res = fmap (fmap toRich) $
            decode treelangParser txt
  dbgPrintLn lvl "Result of parsing:"
  case res of
     Left err -> error err
     Right ls -> do
       ls' <- handleRequire file ls
       return $ runSyM 0 $ parseSExp ls'

-- | Change regular applications into data constructor syntax.
tagDataCons :: DDefs Ty2 -> L Exp2 -> L Exp2
tagDataCons ddefs = go allCons
  where
   allCons = S.fromList [ (toVar con)
                        | DDef{dataCons} <- M.elems ddefs
                        , (con,_tys) <- dataCons ]

   go :: Set Var -> L Exp2 -> L Exp2
   go cons (L p ex) = L p $
     case ex of
       Ext _ -> ex
       AppE v [l] (L _ (MkProdE ls))
                    -- FIXME: check the type to determine if this is packed/unpacked:
                    | S.member v cons -> DataConE l (fromVar v) (L.map (go cons) ls)
       AppE v [l] e | S.member v cons -> DataConE l (fromVar v) [go cons e]
                    | otherwise       -> AppE v [l] (go cons e)
       AppE v l e -> AppE v l (go cons e)
       LetE (v,l,t,rhs) bod ->
         let go' = if S.member v cons
                      then go (S.delete v cons)
                      else go cons
         in LetE (v,l,t,go' rhs) (go' bod)
       ------------boilerplate------------
       VarE v          -> VarE v
       LitSymE v       -> LitSymE v
       LitE _          -> ex
       PrimAppE p ls   -> PrimAppE p $ L.map (go cons) ls
       ProjE i e  -> ProjE i (go cons e)
       CaseE e ls -> CaseE (go cons e) (L.map (\(c,vs,er) -> (c,vs,go cons er)) ls)
       MkProdE ls     -> MkProdE $ L.map (go cons) ls
       DataConE loc k ls -> DataConE loc k $ L.map (go cons) ls
       TimeIt e t b -> TimeIt (go cons e) t b
       IfE a b c -> IfE (go cons a) (go cons b) (go cons c)

       MapE  (v,t,e) bod -> MapE (v,t, go cons e) (go cons bod)
       FoldE (v1,t1,e1) (v2,t2,e2) b -> FoldE (v1,t1,go cons e1) (v2,t2,go cons e2) (go cons b)

insertFD :: L2.FunDef -> NewFuns -> NewFuns
insertFD d = M.insertWith err' (funname d) d
  where
   err' = error $ "insertFD: function definition with duplicate name: "++show (funname d)

fromListFD :: [L2.FunDef] -> NewFuns
fromListFD = L.foldr insertFD M.empty


-- | Convert from raw, unstructured S-Expression into the program datatype we expect.
parseSExp :: [Sexp] -> SyM Prog
parseSExp ses = 
  do prog@Prog {ddefs} <- go ses [] [] [] Nothing
     return $ mapExprs (tagDataCons ddefs) prog

  where

   -- WARNING: top-level constant definitions are INLINED everywhere.
   inlineConstDefs [] p = p
   inlineConstDefs ((vr,_ty,rhs) : cds) p =
       inlineConstDefs cds $
        mapExprs (L1.subst vr rhs) p

   -- Processes an sexpression while accumulating data, function, and constant defs.
   go xs dds fds cds mn =
    case xs of
     [] -> return $
           inlineConstDefs cds $
           Prog (fromListDD dds) (fromListFD fds) mn

     -- IGNORED!:
     (Ls0 (A _ "provide":_) : rst) -> go rst dds fds cds mn
     (Ls0 (A _ "require":_) : rst) -> go rst dds fds cds mn

     (Ls0 (A _ "data": A _ tycon : cs) : rst) ->
         go rst (DDef (textToVar tycon) (L.map docasety cs) : dds) fds cds mn
     -- (Ls0 [A _ "define", funspec, A _ ":", retty, bod] : rst)
     --    |  RSList (A _ name : args) <- funspec
     --    -> do
     --     let bod' = exp bod
     --         args' = L.map (\(RSList [id, A _ ":",t]) -> (getSym id, typ t))
     --                           args
     --     (arg,ty,bod'') <-
     --           case args' of
     --             []   -> (,voidTy,bod') <$> gensym (toVar "void")
     --             [(a,t)] -> pure (a,t,bod')
     --             _    -> do let (vs,ts) = unzip args'
     --                        vr <- gensym (toVar (L.concat $ L.intersperse "_" $
     --                                             L.map fromVar vs))
     --                        let ty = ProdTy ts
     --                            newbod = tuplizeRefs vr vs bod'
     --                        return (vr,ty,newbod)
     --     -- Here we directly desugar multiple arguments into a tuple
     --     -- argument.
     --     go rst dds (FunDef { funName  = textToVar name
     --                        , funArg   = (arg, ty)
     --                        , funRetTy = typ retty
     --                        , funBody  = bod''
     --                        } : fds)
     --        cds mn

     -- Top-level definition instead of a function.
     (Ls0 [A _ "define", A _ topid, A _ ":", ty, bod] : rst) ->
         go rst dds fds ((textToVar topid,ty,exp bod) : cds) mn

     (Ls0 [A _ "define", _args, _bod] : _) -> error$ "Function is missing return type:\n  "++prnt (head xs)
     (Ls0 (A _ "define" : _) : _) -> error$ "Badly formed function:\n  "++prnt (head xs)

     (Ls0 (A _ "data" : _) : _) -> error$ "Badly formed data definition:\n  "++prnt (head xs)

     (Ls3 _ "module+" _ bod : rst) -> go (bod:rst) dds fds cds mn

     (ex : rst) ->
       let ex' = exp ex
       in go rst dds fds cds (case mn of
                            Nothing -> Just (ex', undefined)
                            Just x  -> error$ "Two main expressions: "++
                                             sdoc x++"\nAnd:\n"++prnt ex)

    
exp :: Sexp -> L Exp2
exp se =
 case se of
   A l "True"  -> L (toLoc l) trueE
   A l "False" -> L (toLoc l) falseE

   Ls0 ((A l "and") : args)  -> go args
     where
       go :: [Sexp] -> L Exp2
       go [] = loc l trueE
       go (x:xs) = loc l $ IfE (exp x) (go xs) (L NoLoc falseE)

   Ls0 ((A l "or") : args)  -> go args
     where
       go :: [Sexp] -> L Exp2
       go [] = loc l falseE
       go (x:xs) = loc l $ IfE (exp x) (loc l trueE) (go xs)

   Ls4 l "if" test conseq altern ->
     loc l $ IfE (exp test) (exp conseq) (exp altern)

   Ls2 l "quote" (A _ v) -> loc l $ LitSymE (textToVar v)

   -- Any other naked symbol is a variable:
   A loc v          -> L (toLoc loc) $ VarE (textToVar v)
   G loc (HSInt n)  -> L (toLoc loc) $ LitE (fromIntegral n)

   -- | This type gets replaced later in flatten:
   Ls2 l "time" arg -> loc l $ TimeIt (exp arg) (L1.PackedTy "DUMMY_TY" "") False

   -- | This variant inserts a loop, controlled by the iters
   -- argument on the command line.
   Ls2 l "iterate" arg -> loc l $ TimeIt (exp arg) (L1.PackedTy "DUMMY_TY" "") True

   Ls0 (A l "case": scrut: cases) ->
     loc l $ CaseE (exp scrut) (L.map docase cases)

   Ls3 l "letloc" (Ls0 [A _ nam, letexpr]) bod ->
       loc l $ Ext $ LetLocE (textToVar nam) (dolocexpr letexpr) (exp bod)

   Ls3 l "letpacked" (Ls0 [A _ x, ty, letexp]) bod ->
       let ty' = typ ty
       in loc l $ LetE  (textToVar x, [L1.getPackedLoc ty'], ty', exp letexp) (exp bod)

   Ls0 [A l "letregion", A _ r, bod] ->
       loc l $ Ext $ LetRegionE (VarR $ textToVar r) (exp bod)

   Ls0 (A l p : ls) | isPrim p -> loc l $ PrimAppE (prim p) $ L.map exp ls

   Ls3 l "vector-ref" evec (G _ (HSInt ind)) ->
       loc l $ ProjE (fromIntegral ind) (exp evec)
   Ls0 (A l "vector" : es) -> loc l $ MkProdE $ L.map exp es

   -- Dictionaries require type annotations for now.  No inference!
   Ls3 l "ann" (Ls1 (A _ "empty-dict")) (Ls2 _ "SymDict" ty) ->
       loc l $ PrimAppE (L1.DictEmptyP $ typ ty) []

   Ls4 l "insert" d k (Ls3 _ "ann" v ty) ->
       loc l $ PrimAppE (L1.DictInsertP $ typ ty) [(exp d),(exp k),(exp v)]

   Ls3 l "ann" (Ls3 _ "lookup" d k) ty ->
       loc l $ PrimAppE (L1.DictLookupP $ typ ty) [(exp d),(exp k)]

   Ls3 l "ann" (Ls3  _ "has-key?" d k) ty ->
     loc l $ PrimAppE (L1.DictHasKeyP $ typ ty) [(exp d),(exp k)]

   -- L [A "error",arg] ->
   Ls3 l "ann" (Ls2 _ "error" arg) ty ->
      case arg of
        G _ (HSString str) -> loc l $ PrimAppE (L1.ErrorP (T.unpack str) (typ ty)) []
        _ -> error$ "bad argument to 'error' primitive: "++prnt arg

   -- Other annotations are dropped:
   Ls3 _ "ann" e _ty -> exp e

   Ls0 (A _ kwd : _args) | isKeyword kwd ->
      error $ "Error reading treelang.  Badly formed expression:\n "++prnt se

   ----------------------------------------
   -- If NOTHING else matches, we are an application.  Be careful we didn't miss anything:
   Ls0 (A l rator : rands) ->
     let app = (loc l) . AppE (textToVar rator) []
     in case rands of
         [] -> app (L NoLoc $ MkProdE [])
         [rand] -> app (exp rand)
         _ -> app (L NoLoc $ MkProdE (L.map exp rands))

   _ -> error $ "Expression form not handled (yet):\n  "++
               show se ++ "\nMore concisely:\n  "++ prnt se

-- | One case of a case expression
docase :: Sexp -> (DataCon,[(Var,Var)], L Exp2)
docase s =
  case s of
    RSList [ RSList (A _ con : args)
           , rhs ]
      -> (textToDataCon con, L.map f args, exp rhs)
    _ -> error$ "bad clause in case expression\n  "++prnt s
 where
   f (RSList [A _ arg, A _ l]) = (textToVar arg, textToVar l)
   f x = error $ "Expected pattern match to be pairs of (argument, location), got:\n" ++ (show x)

dolocexpr :: Sexp -> LocExp
dolocexpr s =
    case s of
      RSList [A _ "start", A _ r] -> StartOfLE $ VarR $ textToVar r
      RSList [A _ "+", A _ "1", A _ l] -> AfterConstantLE 1 $ textToVar l
      RSList [A _ "+", (RSList [A _ "sizeof", A _ v]), A _ l] -> AfterVariableLE (textToVar v) (textToVar l)
      _ -> error $ "Malformed locexp:\n" ++ (show s)

letbind :: Sexp -> (Var,[l],Ty2, L Exp2)
letbind s =
  case s of
   RSList [A _ vr, A _ ":",
           ty, rhs]
     -> (textToVar vr, [], typ ty, exp rhs)
   _ -> error $ "Badly formed let binding:\n  "++prnt s

bracketHacks :: Text -> Text
bracketHacks = T.map $ \case '[' -> '('
                             ']' -> ')'
                             x   -> x

-- Ideally, we'd extend the parser to ignore #lang lines.
-- But for now we'll just do that in a preprocessing hack.
treelangParser :: SExprParser (SC.Located HaskLikeAtom) (SExpr (SC.Located  HaskLikeAtom))
treelangParser =
    let langline = string "#lang " *> eatline
        comment  = string ";"      *> eatline
        eatline  = manyTill anyChar newline *> pure ()
        quote expr     = SCons (SAtom "quote") (SCons expr SNil)
        addQuoteReader = addReader '\'' (\ parse -> fmap quote parse)
    in
    -- setCarrier (return . asRich) $
        setComment (comment <|> langline) $
        addQuoteReader locatedHaskLikeParser

docasety :: Sexp -> (DataCon,[(IsBoxed,Ty2)])
docasety s =
  case s of
    (RSList ((A _ id) : tys)) -> (textToDataCon id, L.map ((False,) . typ) tys)
    _ -> error$ "Badly formed variant of datatype:\n "++prnt s
