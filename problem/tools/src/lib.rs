#![allow(non_snake_case, unused_macros)]

use itertools::Itertools;
use proconio::input;
use rand::prelude::*;
use std::io::Read;
use std::io::Write;
use std::io::{prelude::*, BufReader};
use std::ops::RangeBounds;
use std::process::ChildStdout;
use std::vec;
use svg::node::{
    element::{Circle, Group, Line, Rectangle, Style, Title, Symbol, Use, Text},
    Blob,
};

pub trait SetMinMax {
    fn setmin(&mut self, v: Self) -> bool;
    fn setmax(&mut self, v: Self) -> bool;
}
impl<T> SetMinMax for T
where
    T: PartialOrd,
{
    fn setmin(&mut self, v: T) -> bool {
        *self > v && {
            *self = v;
            true
        }
    }
    fn setmax(&mut self, v: T) -> bool {
        *self < v && {
            *self = v;
            true
        }
    }
}

#[macro_export]
macro_rules! mat {
	($($e:expr),*) => { Vec::from(vec![$($e),*]) };
	($($e:expr,)*) => { Vec::from(vec![$($e),*]) };
	($e:expr; $d:expr) => { Vec::from(vec![$e; $d]) };
	($e:expr; $d:expr $(; $ds:expr)+) => { Vec::from(vec![mat![$e $(; $ds)*]; $d]) };
}

#[derive(Clone, Debug)]
pub struct Input {
    pub N: usize,
    pub M: usize,
    pub T: usize,
    pub si: usize,
    pub sj: usize,
    pub S: Vec<String>,
}

impl std::fmt::Display for Input {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        writeln!(f, "{} {} {} {} {}", self.N, self.M, self.T, self.si, self.sj)?;
        for i in 0..self.N {
            writeln!(f, "{}", self.S[i])?;
        }
        Ok(())
    }
}

pub fn parse_input(f: &str) -> Input {
    let f = proconio::source::once::OnceSource::from(f);
    input! {
        from f,
        N: usize,
        M: usize,
        T: usize,
        si: usize,
        sj: usize,
        S: [String; N],
    }
    Input {
        N,
        M,
        T,
        si,
        sj,
        S,
    }
}

pub fn read<T: Copy + PartialOrd + std::fmt::Display + std::str::FromStr, R: RangeBounds<T>>(
    token: Option<&str>,
    range: R,
) -> Result<T, String> {
    if let Some(v) = token {
        if let Ok(v) = v.parse::<T>() {
            if !range.contains(&v) {
                Err(format!("Out of range: {}", v))
            } else {
                Ok(v)
            }
        } else {
            Err(format!("Parse error: {}", v))
        }
    } else {
        Err("Unexpected EOF".to_owned())
    }
}

pub const DIJ: [(usize, usize); 4] = [(!0, 0), (1, 0), (0, !0), (0, 1)];
pub const DIR: [char; 4] = ['U', 'D', 'L', 'R'];

#[derive(Clone, Debug, Copy)]
pub enum Action {
    Move(usize),
    Shoot(usize),
    Pass,
}

pub struct Output {
    pub out: Vec<Action>,
}

pub fn parse_output(input: &Input, f: &str) -> Result<Output, String> {
    let mut ss = f.split_whitespace().peekable();
    let K = read(ss.next(), 0..=input.T)?;
    let mut out = vec![];
    while ss.peek().is_some() {
        let mode = read(ss.next(), 1..=3)?;
        if mode == 1 {
            // Move
            let d = read(ss.next(), 'A'..='Z')?;
            let Some(d) = DIR.iter().position(|&dir| dir == d) else {
                return Err(format!("Invalid direction: {}", d));
            };
            out.push(Action::Move(d));
        } else if mode == 2 {
            // Shoot
            let d = read(ss.next(), 'A'..='Z')?;
            let Some(d) = DIR.iter().position(|&dir| dir == d) else {
                return Err(format!("Invalid direction: {}", d));
            };
            out.push(Action::Shoot(d));
        } else if mode == 3 {
            // Pass
            out.push(Action::Pass);
        } else {
            return Err(format!("Invalid mode: {}", mode));
        }
    }
    if out.len() != K {
        return Err(format!(
            "Output length mismatch: expected {}, got {}",
            K,
            out.len()
        ));
    }
    Ok(Output { out })
}

pub fn gen(seed: u64) -> Input {
    let mut rng = rand_chacha::ChaCha20Rng::seed_from_u64(seed);
    let N = 20 as usize;
    let T = 250 as usize;
    let N_i32 = N as i32;
    let M = rng.gen_range(0i32..=30i32) as usize;
    let si = rng.gen_range(0i32..N_i32) as usize;
    let sj = rng.gen_range(0i32..N_i32) as usize;
    let mut S = vec![vec!['.'; N]; N];
    let mut M_rest = M as i32;
    while M_rest > 0 {
        let i = rng.gen_range(0i32..N_i32) as usize;
        let j = rng.gen_range(0i32..N_i32) as usize;
        if S[i][j] == '#' {
            continue;
        }
        if i == si && j == sj {
            continue;
        }
        S[i][j] = '#';
        // 床マスの連結判定を行う
        let mut visited = vec![vec![false; N]; N];
        let mut stack = vec![];
        // スタート地点をスタックに追加
        for pos in 0..N*N {
            let x = pos / N;
            let y = pos % N;
            if S[x][y] == '.' {
                stack.push((x, y));
                visited[x][y] = true;
                break;
            }
        }
        let dx = vec![-1, 0, 1, 0] as Vec<i32>;
        let dy = vec![0, -1, 0, 1] as Vec<i32>;
        while let Some((x, y)) = stack.pop() {
            for d in 0..4 {
                let nx = x as i32 + dx[d];
                let ny = y as i32 + dy[d];
                if nx < 0 || nx >= N_i32 || ny < 0 || ny >= N_i32 {
                    continue;
                }
                if visited[nx as usize][ny as usize] {
                    continue;
                }
                if S[nx as usize][ny as usize] == '#' {
                    continue;
                }
                visited[nx as usize][ny as usize] = true;
                stack.push((nx as usize, ny as usize));
            }
        }
        // 床マスの連結判定
        let mut ok = true;
        for pos in 0..N*N {
            let x = pos / N;
            let y = pos % N;
            if S[x][y] == '.' && !visited[x][y] {
                ok = false;
                break;
            }
        }
        if !ok {
            S[i][j] = '.';
            continue;
        }
        M_rest -= 1;
    }
    Input {
        N,
        M,
        T,
        si,
        sj,
        S: S.iter().map(|s| s.iter().collect()).collect(),
    }
}

pub fn compute_score(input: &Input, out: &Output) -> (i64, String) {
    let (mut score, err, _) = compute_score_details(input, &out);
    if err.len() > 0 {
        score = 0;
    }
    (score, err)
}


#[derive(Clone, Debug)]
pub struct State {
    pub board: Vec<Vec<char>>,
    pub pi: usize,
    pub pj: usize,
    pub power: usize,
    pub last_painted: Vec<(usize, usize)>,
}


pub fn compute_score_details(input: &Input, out: &Output) -> (i64, String, State) {
    let mut state = State {
        board: input.S.iter().map(|s| s.chars().collect::<Vec<char>>()).collect::<Vec<Vec<char>>>(),
        pi: input.si,
        pj: input.sj,
        power: 0,
        last_painted: vec![],
    };
    for action in out.out.iter() {
        state.last_painted = vec![];
        match *action {
            Action::Move(dir) => {
                //移動
                let (di, dj) = DIJ[dir];
                let pi = state.pi + di;
                let pj = state.pj + dj;
                if pi >= 0 && pi < input.N && pj >= 0 && pj < input.N && state.board[pi][pj] != '#' {
                    state.pi = pi;
                    state.pj = pj;
                }
            }
            Action::Shoot(dir) => {
                //射撃
                let (di, dj) = DIJ[dir];
                let mut x = state.pi;
                let mut y = state.pj;;
                for _ in 0..=state.power {
                    if x < 0 || x >= input.N || y < 0 || y >= input.N || state.board[x][y] == '#' {
                        break; // 範囲外または壁
                    }
                    if state.board[x][y] == '.' {
                        state.board[x][y] = 'o'; // インクを塗る
                        state.last_painted.push((x, y));
                    }
                    x += di;
                    y += dj;
                }
                state.power /= 2; // パワーを半分にする
            }
            Action::Pass => {}
        }
        state.power += 1;
    }

    //スコア計算
    let mut score = input.M;
    for i in 0..input.N {
        for j in 0..input.N {
            if state.board[i][j] == 'o' {
                score += 1;
            }
        }
    }
    if score == input.N * input.N {
        let K = out.out.len();
        score += input.T - K;
    }

    (score as i64, String::new(), state)
}

/// 0 <= val <= 1
pub fn color(mut val: f64) -> String {
    val.setmin(1.0);
    val.setmax(0.0);
    let (r, g, b) = if val < 0.5 {
        let x = val * 2.0;
        (
            30. * (1.0 - x) + 144. * x,
            144. * (1.0 - x) + 255. * x,
            255. * (1.0 - x) + 30. * x,
        )
    } else {
        let x = val * 2.0 - 1.0;
        (
            144. * (1.0 - x) + 255. * x,
            255. * (1.0 - x) + 30. * x,
            30. * (1.0 - x) + 70. * x,
        )
    };
    format!("#{:02x}{:02x}{:02x}", r.round() as i32, g.round() as i32, b.round() as i32)
}

pub fn rect(x: usize, y: usize, w: usize, h: usize, fill: &str) -> Rectangle {
    Rectangle::new()
        .set("x", x)
        .set("y", y)
        .set("width", w)
        .set("height", h)
        .set("fill", fill)
}

pub fn group(title: String) -> Group {
    Group::new().add(Title::new(title))
}

pub fn vis_default(input: &Input, out: &Output) -> (i64, String, String) {
    let default_ink_color: &String = &"#008a7c".to_string();
    let (mut score, err, svg) = vis(input, &out.out, default_ink_color);
    if err.len() > 0 {
        score = 0;
    }
    (score, err, svg)
}

// https://www.svgrepo.com/svg/74640/shooting
const SHOOTER: &str = r#"<g>
    <path d="M74.341,49.133c2.28-8.982,10.41-15.655,20.091-15.655h16.166c0.731-2.395,1.127-4.937,1.127-7.571    C111.725,11.599,100.126,0,85.818,0S59.912,11.599,59.912,25.907C59.912,36.092,65.792,44.9,74.341,49.133z"/>
    <path d="m177.899,33.478c0.602-3.969-0.716-8.157-3.892-11.081-5.078-4.678-12.987-4.349-17.662,0.73l-9.529,10.35c12.902,0.001 19.829,0.001 31.083,0.001z"/>
    <path d="m258.183,44.978h-6.857v-4.5c0-3.313-2.686-6-6-6-3.313,0-6,2.687-6,6v4.5h-52.394v0.026c0.796,0.728 1.554,1.505 2.257,2.343 4.211,5.02 6.131,11.379 5.652,17.631h63.342c5.522,0 10-4.478 10-10s-4.478-10-10-10z"/>
    <path d="m85.682,54.228v13.707l39.371,1.228 28.239-23.685h-58.86c-4.832,7.10543e-15-8.75,3.917-8.75,8.75z"/>
    <path d="m178.733,53.778c-4.671-4.181-11.654-4.195-16.342-0.269-0.002,0.002-0.004,0.003-0.007,0.005l-33.128,27.786c-10.448-3.079-55.574-15.809-55.574-15.809v-5.921h-3.604c-9.665,0-17.501,7.835-17.501,17.501v89.604l-1.87,44.708-24.993,60.661c-3.155,7.659 0.495,16.427 8.155,19.583 7.653,3.155 16.425-0.492 19.583-8.155l26-63.105c0.666-1.617 1.045-3.339 1.118-5.087 1.261-30.127 1.733-41.293 1.906-45.52 0.066-1.618 1.397-2.898 3.017-2.898h0.002c1.291,0 2.445,0.806 2.889,2.018l14.835,40.447-13.834,65.324c-1.716,8.104 3.463,16.065 11.567,17.782 8.107,1.715 16.065-3.465 17.782-11.567l14.728-69.546c0.584-2.758 0.379-5.625-0.592-8.272l-14.083-38.398v-49.263c-8.317-4.729-32.374-18.407-40.524-23.041l50.36,14.829c4.025,1.185 8.405,0.236 11.564-2.414l38.264-32.093c5.741-4.814 6.068-13.715 0.282-18.89z"/>
</g>"#;

pub fn vis(input: &Input, out: &[Action], ink_color: &String) -> (i64, String, String) {
    let D = 600 / input.N;
    let W = input.N * D;
    let (score, err, state) = compute_score_details(input, &Output { out: out.to_vec() });
    let mut doc = svg::Document::new()
        .set("id", "vis")
        .set("viewBox", (-5, -5, W + 10, W + 10))
        .set("width", W + 10)
        .set("height", W + 10 + 70)
        .set("style", "background-color:white");
    doc = doc.add(Style::new(format!(
        "text {{text-anchor: middle;dominant-baseline: central;}}"
    )));
    doc = doc.add(
        Symbol::new()
            .set("id", "shooter")
            .set("viewBox", (0, 0, 514.962, 514.962))
            .add(Blob::new(SHOOTER)),
    );

    for i in 0..input.N {
        for j in 0..input.N {
            let mut group = group(format!("({}, {})", i, j));
            let mut rect = rect(
                j * D,
                i * D,
                D,
                D,
                if state.board[i][j] == '#' { "#111111" } else if state.board[i][j] == 'o' { ink_color } else { "white" },
            )
            .set("stroke", "black")
            .set("stroke-width", 1);
            if state.board[i][j] == 'o' {
                rect = rect.set("fill-opacity", 0.5);
            }
            group = group.add(rect);
            if (i, j) == (state.pi, state.pj) {
                let shooter = Use::new()
                    .set("x", j * D + D / 8)
                    .set("y", i * D + D / 8)
                    .set("width", D * 3 / 2)
                    .set("height", D * 3 / 2)
                    .set("href", "#shooter")
                    .set("fill", "#000000");
                group = group.add(shooter);
            }

            let mut is_last_painted = false;
            for (x, y) in &state.last_painted {
                if *x == i && *y == j {
                    is_last_painted = true;
                    break;
                }
            }
            if is_last_painted {
                let border = Rectangle::new()
                    .set("x", j * D + 1)
                    .set("y", i * D + 1)
                    .set("width", D - 2)
                    .set("height", D - 2)
                    .set("fill", "none")
                    .set("stroke", "red")
                    .set("stroke-width", 2);
                group = group.add(border);
            }

            doc = doc.add(group);
        }
    }

    //現在のインクパワーを表示
    let power_bar = Rectangle::new()
        .set("x", D)
        .set("y", W + 10)
        .set("width", W - 2 * D)
        .set("height", D)
        .set("fill", "none")
        .set("stroke", "black")
        .set("stroke-width", 2);
    let power_ratio = std::cmp::min(state.power, 20) as f64 / 20.0;
    let power_bar_fill = Rectangle::new()
        .set("x", D + 1)
        .set("y", W + 10 + 1)
        .set("width", ((W as f64 - 2.0 * D as f64 - 2.0) * power_ratio) as usize)
        .set("height", D - 2)
        .set("fill", ink_color.to_string());
    let power_text = Text::new(format!("Power = {}", state.power))
        .set("x", D + 470)
        .set("y", W + 25)
        .set("font-size", "16px")
        .set("fill", "black")
        .set("text-anchor", "start");
    doc = doc.add(power_bar)
        .add(power_bar_fill)
        .add(power_text);

    (score, err, doc.to_string())
}


fn read_line(stdout: &mut BufReader<ChildStdout>, local: bool) -> Result<String, String> {
    loop {
        let mut out = String::new();
        match stdout.read_line(&mut out) {
            Ok(0) | Err(_) => {
                return Err(format!("Your program has terminated unexpectedly"));
            }
            _ => (),
        }
        if local {
            print!("{}", out);
        }
        let v = out.trim();
        if v.len() == 0 {
            continue;
        }
        return Ok(v.to_owned());
    }
}

pub fn exec(p: &mut std::process::Child, local: bool) -> Result<i64, String> {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input).unwrap();
    let mut input = parse_input(&input);
    let mut stdin = std::io::BufWriter::new(p.stdin.take().unwrap());
    let mut stdout = std::io::BufReader::new(p.stdout.take().unwrap());
    let _ = writeln!(
        stdin,
        "{} {} {} {} {}",
        input.N, input.M, input.T, input.si, input.sj
    );
    for i in 0..input.N {
        let _ = writeln!(stdin, "{}", input.S[i]);
    }
    let _ = stdin.flush();

    let mut f = String::new();
    let line = read_line(&mut stdout, local)?;
    let mut tokens = line.split_whitespace();
    let K = read(tokens.next(), 0..=input.T)?;
    f.push_str(&K.to_string());
    f.push(' ');
    for _ in 0..K {
        let line = read_line(&mut stdout, local)?;
        f.push_str(&line);
        f.push(' ');
    }
    let out = match parse_output(&input, &f) {
        Ok(out) => out,
        Err(err) => return Err(err),
    };
    let (score, err, state) = compute_score_details(&input, &out);
    if err.len() > 0 {
        return Err(err);
    }
    Ok(score as i64)
}
